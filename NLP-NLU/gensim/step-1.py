from __future__ import print_function
from gensim.corpora import WikiCorpus
import jieba
import codecs
import os
import six
from gensim.models import Word2Vec
from gensim.models.word2vec import LineSentence
import multiprocessing



import sys  
reload(sys)  
sys.setdefaultencoding('utf8')   
reload(sys)

 
class Config:
    data_path = './'
    zhwiki_bz2 = 'zhwiki-latest-pages-articles.xml.bz2'
    zhwiki_raw = 'zhwiki_raw.txt'
    #zhwiki_raw_t2s = 'zhwiki_raw_t2s.txt'
    zhwiki_raw_t2s = 'zhwiki_raw.txt'
    zhwiki_seg_t2s = 'zhwiki_seg.txt'
    embedded_model_t2s = 'embedding_model_t2s/zhwiki_embedding_t2s.model'
    embedded_vector_t2s = 'embedding_model_t2s/vector_t2s'
 
 
def dataprocess(_config):
    i = 0
    if six.PY3:
        output = open(os.path.join(_config.data_path, _config.zhwiki_raw), 'w')
    output = codecs.open(os.path.join(_config.data_path, _config.zhwiki_raw), 'w')
    wiki = WikiCorpus(os.path.join(_config.data_path, _config.zhwiki_bz2), lemmatize=False, dictionary={})
    for text in wiki.get_texts():
        if six.PY3:
            output.write(b' '.join(text).decode('utf-8', 'ignore') + '\n')
        else:
            output.write(' '.join(text) + '\n')
        i += 1
        if i % 10000 == 0:
            print('Saved ' + str(i) + ' articles')
    output.close()
    print('Finished Saved ' + str(i) + ' articles')

config = Config()
#dataprocess(config)





def is_alpha(tok):
    try:
        return tok.encode('ascii').isalpha()
    except UnicodeEncodeError:
        return False


def zhwiki_segment(_config, remove_alpha=True):
    i = 0
    if six.PY3:
        output = open(os.path.join(_config.data_path, _config.zhwiki_seg_t2s), 'w', encoding='utf-8')
    output = codecs.open(os.path.join(_config.data_path, _config.zhwiki_seg_t2s), 'w', encoding='utf-8')
    print('Start...')
    with codecs.open(os.path.join(_config.data_path, _config.zhwiki_raw_t2s), 'r', encoding='utf-8') as raw_input:
        for line in raw_input.readlines():
            line = line.strip()
            i += 1
            print('line ' + str(i))
            text = line.split()
            if True:
                text = [w for w in text if not is_alpha(w)]
            word_cut_seed = [jieba.cut(t) for t in text]
            tmp = ''
            for sent in word_cut_seed:
                for tok in sent:
                    tmp += tok + ' '
            tmp = tmp.strip()
            if tmp:
                output.write(tmp + '\n')
        output.close()

zhwiki_segment(config)

