import re
import time
import io
import sys
from collections import defaultdict

tokensFilename = sys.argv[1] 
labelsFilename = sys.argv[2] 
outputFilename = sys.argv[3]

tokensFile = io.open(tokensFilename, encoding='utf8', mode='r')
labelsFile = io.open(labelsFilename, encoding='utf8', mode='r')
outputFile = io.open(outputFilename, encoding='utf8', mode='w')

counter = 0
for tokensLine in tokensFile:
  labelsLine = labelsFile.readline()
  counter += 1
  tokens = tokensLine.strip().split(' ')
  labels = labelsLine.strip().split(' ')
  if(len(tokens) != len(labels)):
    print 'at input file, line # ', counter
    print 'len(tokens) != len(labels) ', len(tokens), len(labels)
    print labels
    print tokens
    assert(False)
  for i in range(0, len(tokens)):
    if i > 0:
      outputFile.write(u' ')
    outputFile.write(u'{0}/{1}'.format(tokens[i], labels[i]))
  outputFile.write(u'\n')

tokensFile.close()
labelsFile.close()
outputFile.close()
