import math
import models
import tensorflow as tf
import numpy as np
import utils
from tensorflow import flags
import tensorflow.contrib.slim as slim
FLAGS = flags.FLAGS

class DeepCnnDeepCombineChainModel(models.BaseModel):
  """A softmax over a mixture of logistic models (with L2 regularization)."""

  def cnn(self, 
          model_input, 
          l2_penalty=1e-8, 
          num_filters = [128,128,256],
          filter_sizes = [1,2,3], 
          sub_scope="",
          **unused_params):
    max_frames = model_input.get_shape().as_list()[1]
    num_features = model_input.get_shape().as_list()[2]

    shift_inputs = []
    for i in xrange(max(filter_sizes)):
      if i == 0:
        shift_inputs.append(model_input)
      else:
        shift_inputs.append(tf.pad(model_input, paddings=[[0,0],[i,0],[0,0]])[:,:max_frames,:])

    cnn_outputs = []
    for nf, fs in zip(num_filters, filter_sizes):
      sub_input = tf.concat(shift_inputs[:fs], axis=2)
      sub_filter = tf.get_variable(sub_scope+"filter-len%d"%fs, 
                       shape=[num_features*fs, nf], dtype=tf.float32, 
                       initializer=tf.truncated_normal_initializer(mean=0.0, stddev=0.1), 
                       regularizer=tf.contrib.layers.l2_regularizer(l2_penalty))
      cnn_outputs.append(tf.einsum("ijk,kl->ijl", sub_input, sub_filter))

    cnn_output = tf.concat(cnn_outputs, axis=2)
    return cnn_output

  def deep_cnn(self, 
          model_input, 
          l2_penalty=1e-8, 
          num_layers=3,
          num_filters = [[128,128,256],[128,128],[128,128]],
          filter_sizes = [[1,2,3],[2,3],[2,3]], 
          sub_scope="",
          **unused_params):
    max_frames = model_input.get_shape().as_list()[1]
    num_features = model_input.get_shape().as_list()[2]

    cnn_outputs = []
    time_pooled = model_input
    for i in xrange(num_layers):
      cnn_output = self.cnn(time_pooled, num_filters=num_filters[i], 
                            filter_sizes=filter_sizes[i], sub_scope=sub_scope+"cnn%d"%i)
      cnn_outputs.append(cnn_output)
      if i+1 < num_layers:
        time_pooled = tf.nn.pool(cnn_output, window_shape=[2], 
                                 pooling_type="MAX", padding="VALID", strides=[2])

    return cnn_outputs

  def create_model(self, model_input, vocab_size, num_frames, num_mixtures=None,
                   dropout=False, keep_prob=None, noise_level=None,
                   l2_penalty=1e-8, sub_scope="", original_input=None, **unused_params):
    num_supports = FLAGS.num_supports
    num_layers = FLAGS.deep_chain_layers
    relu_cells = FLAGS.deep_chain_relu_cells
    cnn_size = FLAGS.deep_cnn_base_size
    max_frames = model_input.get_shape().as_list()[1]

    relu_layers = []
    support_predictions = []

    mask = self.get_mask(max_frames, num_frames)
    mean_input = tf.einsum("ijk,ij->ik", model_input, mask) \
                      / tf.expand_dims(tf.cast(num_frames, dtype=tf.float32), dim=1)
    mean_relu = slim.fully_connected(
          mean_input,
          relu_cells,
          activation_fn=tf.nn.relu,
          weights_regularizer=slim.l2_regularizer(l2_penalty),
          scope=sub_scope+"mean-relu")
    mean_relu_norm = tf.nn.l2_normalize(mean_relu, dim=1)
    relu_layers.append(mean_relu_norm)

    cnn_outputs = self.deep_cnn(model_input, sub_scope=sub_scope+"deepcnn0",
                                num_layers=3,
                                num_filters = [[cnn_size,cnn_size,cnn_size*2],[cnn_size,cnn_size],[cnn_size,cnn_size]],
                                filter_sizes = [[1,2,3],[2,3],[2,3]])
    max_cnn_output = tf.concat(map(lambda x: tf.reduce_max(x, axis=1), cnn_outputs), axis=1)
    normalized_cnn_output = tf.nn.l2_normalize(max_cnn_output, dim=1)
    next_input = normalized_cnn_output

    for layer in xrange(num_layers):
      sub_prediction = self.sub_model(next_input, vocab_size, sub_scope=sub_scope+"prediction-%d"%layer, 
                                      dropout=dropout, keep_prob=keep_prob, noise_level=noise_level)
      support_predictions.append(sub_prediction)

      sub_relu = slim.fully_connected(
          sub_prediction,
          relu_cells,
          activation_fn=tf.nn.relu,
          weights_regularizer=slim.l2_regularizer(l2_penalty),
          scope=sub_scope+"relu-%d"%layer)
      relu_norm = tf.nn.l2_normalize(sub_relu, dim=1)
      relu_layers.append(relu_norm)

      cnn_outputs = self.deep_cnn(model_input, sub_scope=sub_scope+"deepcnn%d"%(layer+1),
                                  num_layers=3,
                                  num_filters = [[cnn_size,cnn_size,cnn_size*2],[cnn_size,cnn_size],[cnn_size,cnn_size]],
                                  filter_sizes = [[1,2,3],[2,3],[2,3]])
      max_cnn_output = tf.concat(map(lambda x: tf.reduce_max(x, axis=1), cnn_outputs), axis=1)
      normalized_cnn_output = tf.nn.l2_normalize(max_cnn_output, dim=1)
      next_input = tf.concat([mean_input, normalized_cnn_output] + relu_layers, axis=1)

    main_predictions = self.sub_model(next_input, vocab_size, sub_scope=sub_scope+"-main",
                                      dropout=dropout, keep_prob=keep_prob, noise_level=noise_level)
    support_predictions = tf.concat(support_predictions, axis=1)
    return {"predictions": main_predictions, "support_predictions": support_predictions}

  def sub_model(self, model_input, vocab_size, num_mixtures=None, 
                dropout=False, keep_prob=None, noise_level=None,
                l2_penalty=1e-8, sub_scope="", **unused_params):
    num_mixtures = num_mixtures or FLAGS.moe_num_mixtures

    if dropout:
      print "adding dropout to", model_input
      model_input = tf.nn.dropout(model_input, keep_prob=keep_prob)

    gate_activations = slim.fully_connected(
        model_input,
        vocab_size * (num_mixtures + 1),
        activation_fn=None,
        biases_initializer=None,
        weights_regularizer=slim.l2_regularizer(l2_penalty),
        scope="gates-"+sub_scope)
    expert_activations = slim.fully_connected(
        model_input,
        vocab_size * num_mixtures,
        activation_fn=None,
        weights_regularizer=slim.l2_regularizer(l2_penalty),
        scope="experts-"+sub_scope)

    gating_distribution = tf.nn.softmax(tf.reshape(
        gate_activations,
        [-1, num_mixtures + 1]))  # (Batch * #Labels) x (num_mixtures + 1)
    expert_distribution = tf.nn.sigmoid(tf.reshape(
        expert_activations,
        [-1, num_mixtures]))  # (Batch * #Labels) x num_mixtures

    final_probabilities_by_class_and_batch = tf.reduce_sum(
        gating_distribution[:, :num_mixtures] * expert_distribution, 1)
    final_probabilities = tf.reshape(final_probabilities_by_class_and_batch,
                                     [-1, vocab_size])
    return final_probabilities

  def get_mask(self, max_frames, num_frames):
    mask_array = []
    for i in xrange(max_frames + 1):
      tmp = [0.0] * max_frames 
      for j in xrange(i):
        tmp[j] = 1.0
      mask_array.append(tmp)
    mask_array = np.array(mask_array)
    mask_init = tf.constant_initializer(mask_array)
    mask_emb = tf.get_variable("mask_emb", shape = [max_frames + 1, max_frames], 
            dtype = tf.float32, trainable = False, initializer = mask_init)
    mask = tf.nn.embedding_lookup(mask_emb, num_frames)
    return mask
