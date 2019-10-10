#! /usr/bin/env python3

"""Convert a BED6 list of peptides to BED12, removing
non-unique peptides (based on "multiple match" of the same
peptide sequence to different coordinates).
"""

import os
import argparse
import pandas as pd

import pbio.utils.bed_utils as bed_utils

BED12_FIELDS = bed_utils.bed12_field_names
BED10_FIELDS = [f for f in BED12_FIELDS if f not in (['id', 'color'])]
BED6_FIELDS = bed_utils.bed6_field_names


def get_ids(row):
    return '&'.join([row.id, row.seqname, row.strand])


def get_pep_id(bed_id):
    # re-assign pep_id
    return str(bed_id.split('&')[0])


def get_bed12_fields(group):
    # BED style coordinates: we need to take this into account when passing
    # to bed_utils.convert_genomic_coords_to_bed_blocks
    # where coordinates are taken to be INCLUSIVE (e.g., as with GTF)
    # for the rest, we keep as is, since we want to output as BED
    inner = ['{}-{}'.format(start, end - 1) for start, end in zip(group.start.values, group.end.values)]
    coords = ','.join(inner)
    d = bed_utils.convert_genomic_coords_to_bed_blocks(coords)
    ret = {
        'seqname': str(group.seqname.values[0]),
        'start': int(group.start.values[0]),
        'end': int(group.end.values[-1]),
        'id': group.id.values[0],
        'score': int(group.score.values[0]),
        'strand': str(group.strand.values[0]),
        'thick_start': int(group.start.values[0]),
        'thick_end': int(group.end.values[-1]),
        'num_exons': d['num_exons'],
        'exon_lengths': d['exon_lengths'],
        'exon_genomic_relative_starts': d['exon_genomic_relative_starts']
    }
    return pd.Series(ret)


def get_unique_peps(group):
    # pick first row arbitrarily, if the peptide is unique, all rows will be equal anyway
    # matching fields must have the same type!
    vals = group[BED10_FIELDS].values
    equal = (vals == vals[0, :]).all()
    if not equal:
        return
    else:
        ret = {
            'seqname': group.seqname.values[0],
            'start': group.start.values[0],
            'end': group.end.values[-1],
            'id': group.id.values[0],
            'score': group.score.values[0],
            'strand': group.strand.values[0],
            'thick_start': group.start.values[0],
            'thick_end': group.end.values[-1],
            'color': '0',
            'num_exons': group.num_exons.values[0],
            'exon_lengths': group.exon_lengths.values[0],
            'exon_genomic_relative_starts': group.exon_genomic_relative_starts.values[0]
        }
        return pd.Series(ret)


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description="""Convert peptides BED6 to BED12, removing
                                     non-unique matches. Fields must be in the intended BED6
                                     order.""")

    parser.add_argument('-f', '--input-file', help="BED6 file (full path).")
    parser.add_argument('-o', '--output-file', help="Output file (only file name bed.gz)")
    parser.add_argument('-skip', '--skiprows', help="Number of rows to skip, including header"
                                                    "(skipped and overwritten)", type=int, default=0)

    args = parser.parse_args()

    pep = pd.read_csv(args.input_file,
                      header=None,
                      names=BED6_FIELDS,
                      sep='\t',
                      skiprows=args.skiprows)

    pep['score'] = 0
    # create new id from id, chrom and strand (otherwise if there are non-unique peptides, we will
    # not be able to sort the dataframe)
    pep['id'] = pep.apply(get_ids, axis=1)
    # convert to BED6
    bed6 = bed_utils.sort(pep)
    bed6 = bed6[BED6_FIELDS]
    # then to BED12
    bed12 = bed6.groupby(['id']).apply(get_bed12_fields)
    bed12.index.name = None
    # now actually find the unique peptides
    # first add back the correct ids
    bed12['id'] = bed12['id'].apply(get_pep_id)
    bed12 = bed12.groupby(['id']).apply(get_unique_peps)
    # remove the non-unique peptides
    bed12 = bed12[~bed12['id'].isna()]
    bed12.reset_index(inplace=True, drop=True)
    bed12 = bed_utils.sort(bed12)
    bed12 = bed12[BED12_FIELDS]
    bed12[['start', 'end', 'thick_start', 'thick_end', 'num_exons']] = bed12[
        ['start', 'end', 'thick_start', 'thick_end', 'num_exons']].astype(int)
    # write to disk
    path, file = os.path.split(args.input_file)
    file = os.path.join(path, args.output_file)
    bed12.to_csv(file, sep='\t', compression='gzip', index=None)
