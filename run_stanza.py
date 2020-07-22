#!/usr/bin/env python3
import argparse
import re
import os

from stroll.conllu import ConlluDataset, Sentence, Token
import stanza

doc_and_sent_id = re.compile('(([^|]*)\|)?(([^|]*)\|)?(.*)')

parser = argparse.ArgumentParser(
        description='Run the Stanza parser and produce CoNLL output',
        )
parser.add_argument(
        '--output',
        help='Output filename'
        )
parser.add_argument(
        'input',
        nargs='*',
        help='Input files'
        )
parser.add_argument(
        '--nogpu',
        default=False,
        action='store_true',
        help='Disable GPU accelaration'
        )
parser.add_argument(
        '-f',
        '--format',
        choices=['conll2012', 'conllu', 'txt'],
        default='txt'
)

processor_dict = {
    #'mwt': 'alpino',  # needed to get FEATS from the pos processor
    'tokenize': 'alpino',
    'pos': 'combined',
    'lemma': 'combined',
    'depparse': 'combined',
    # 'ner': None
}


def dataset_from_text_files(names=None, dataset=None):
    """
    Parse a set of files, and add them to a ConlluDataset.
    The files are parsed line-by-line, where the following format is assumed:
       doc_id|sent_id|Full text of the sentence.

    doc_id and sent_id are optional.
    The default for the doc_id is the filename
    The default for the sent_id is the index of the sentence in the document.
    If only one is provided, it is assumed to be the sent_id.

    Arguments:
        names:      list of str.  Files to process
        dataset:    ConlluDataset or None. Dataset to add the sentences to.

    Returns:
        ConlluDataset
    """
    if not dataset:
        dataset = ConlluDataset()

    for name in names:
        sent_idx = 0
        with open(name, 'r') as infile:
            for line in infile:
                if len(line.strip())>0:
                    groups = doc_and_sent_id.match(line).groups()
                    if groups[3]:
                        doc_id = groups[1]
                        sent_id = groups[3]
                    elif groups[1]:
                        doc_id = name
                        sent_id = groups[1]
                    else:
                        doc_id = name
                        sent_id = '{:10d}'.format(sent_idx)

                    full_text = groups[4]
                    parsed = nlp(full_text).to_dict()

                    sentence = Sentence()
                    for t in parsed[0]:
                        if 'feats' not in t:
                            t['feats'] = '_'
                        token = Token([
                          t['id'],  # ID
                          t['text'],  # FORM
                          t['lemma'],  # LEMMA
                          t['upos'],  # UPOS
                          t['xpos'],  # XPOS
                          t['feats'],  # FEATS
                          '{}'.format(t['head']),  # HEAD
                          t['deprel'],  # DEPREL
                          '_',  # DEPS
                          '_'  # MISC
                        ])
                        sentence.add(token)

                    sentence.full_text = full_text
                    sentence.doc_id = doc_id
                    sentence.sent_id = sent_id
                    dataset.add(sentence)

                    sent_idx += 1

    return dataset


def parse_dataset(dataset, nlp):
    """
    Parse tokenized dataset with stanza,
    possibly overwriting the lemma, pos, dependency fields.
    """
    for sentence in dataset.sentences:
        tokens = [[t.FORM for t in sentence]]
        parsed = nlp(tokens).to_dict()
        for token, parsed_token in zip(sentence.tokens, parsed[0]):
            token.ID = parsed_token['id']
            token.LEMMA = parsed_token['lemma']
            token.UPOS = parsed_token['upos']
            token.XPOS = parsed_token['xpos']
            token.FEATS = parsed_token.get('feats', '_')
            token.HEAD = '{}'.format(parsed_token['head'])
            token.DEPREL = parsed_token['deprel']
    return dataset

if __name__ == '__main__':
    args = parser.parse_args()

    if args.format == 'txt':
        nlp = stanza.Pipeline('nl', processors=processor_dict, package=None, use_gpu=not args.nogpu)
        dataset = dataset_from_text_files(args.input)
    elif args.format == 'conllu':
        nlp = stanza.Pipeline('nl', processors=processor_dict, package=None, tokenize_pretokenized=True, use_gpu=not args.nogpu)
        dataset = ConlluDataset()
        for input_file in args.input:
            dataset._load(input_file)
        dataset = parse_dataset(dataset, nlp)
    elif args.format == 'conll2012':
        nlp = stanza.Pipeline('nl', processors=processor_dict, package=None, tokenize_pretokenized=True, use_gpu=not args.nogpu)
        dataset = ConlluDataset()
        for input_file in args.input:
            dataset.load_mmax(input_file)
        dataset = parse_dataset(dataset, nlp)

    output  = args.output if args.output is not None else args.input[0]+'_stanza.conll'
    with open(output, 'w') as outfile:
        outfile.write(dataset.__repr__())
