
//
// This is example code from Chapter 8.3 "Header Files" of
// "Programming -- Principles and Practice Using C++" by Bjarne Stroustrup
//

#include "f.h"

//------------------------------------------------------------------------------

int g(int i)
{
    return f(i);
}

//------------------------------------------------------------------------------

int main()
{
    return g(4444);
}

//------------------------------------------------------------------------------

int f(int n)
{
    return n;
}

//------------------------------------------------------------------------------
