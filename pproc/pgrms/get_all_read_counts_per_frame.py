#! /usr/bin/env python3

""" Get all periodic, p-site adjusted read counts for each
frame for each sample, using the ORF profiles. The counts
are for all periodic read fragments, and not only for the
predicted ORFs. If only the counts for the predicted ORFs
are needed, they can easily be obtained from the frame counts
in the prediction files.

Note* The isoform strategy option will be removed.

Functions:
    get_profile
    get_counts
"""

import os
import argparse
import yaml
import csv
import logging
import pandas as pd
import numpy as np

import pbio.ribo.ribo_utils as ribo_utils
import pbio.ribo.ribo_filenames as filenames

import pbio.misc.logging_utils as logging_utils
import pbio.misc.parallel as parallel
import pbio.misc.pandas_utils as pandas_utils

import btea.utils.cl_utils as clu

from rpbp.defaults import metagene_options

logger = logging.getLogger(__name__)

default_num_cpus = 2


def get_profile(sample_name, config, args):
    """ Get the name of the profile file from the given parameters.
    """

    note_str = config.get('note', None)
    is_unique = not ('keep_riboseq_multimappers' in config)

    lengths, offsets = ribo_utils.get_periodic_lengths_and_offsets(config,
                                                                   sample_name,
                                                                   isoform_strategy=args.isoform_strategy,
                                                                   default_params=metagene_options,
                                                                   is_unique=is_unique)

    if len(lengths) == 0:
        msg = ("No periodic read lengths and offsets were found. Try relaxing "
               "min_metagene_profile_count, min_metagene_bf_mean, max_metagene_bf_var, "
               "and/or min_metagene_bf_likelihood.")
        logger.critical(msg)
        return

    profiles = filenames.get_riboseq_profiles(config['riboseq_data'],
                                              sample_name,
                                              length=lengths,
                                              offset=offsets,
                                              is_unique=is_unique,
                                              isoform_strategy=args.isoform_strategy,
                                              note=note_str)

    return profiles


def get_counts(sample_name, sample_name_map, config, args):

    msg = "processing {}...".format(sample_name)
    logger.info(msg)

    mtx = get_profile(sample_name, config, args)

    # we don't need to load as sparse matrix, use numpy and
    # mask based on ORF offset (2nd column), taking into account that
    # mtx format is 1-based
    # skip header, including mtx format specifications

    profiles = np.loadtxt(mtx, skiprows=3)

    m_frame1 = np.where(profiles[:, 1] % 3 == 1)
    m_frame2 = np.where(profiles[:, 1] % 3 == 2)
    m_frame3 = np.where(profiles[:, 1] % 3 == 0)

    frame1 = profiles[m_frame1][:, 2].sum()
    frame2 = profiles[m_frame2][:, 2].sum()
    frame3 = profiles[m_frame3][:, 2].sum()

    ret = {'condition': sample_name_map[sample_name],
           'frame_count': frame1,
           'frame+1_count': frame2,
           'frame+2_count': frame3}

    return pd.Series(ret)


def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                                     description="""Using the ORF profiles, get the distribution
                                     of periodic, p-site adjusted read counts across all profiles,
                                     for each frame and for each sample.""")

    parser.add_argument('config', help="The yaml config file.")

    parser.add_argument('out', help="The output csv.gz file with the counts")

    parser.add_argument('-p', '--num-cpus', help="The number of processors to use",
                        type=int, default=default_num_cpus)

    parser.add_argument('--overwrite', action='store_true')

    clu.add_isoform_strategy(parser)
    logging_utils.add_logging_options(parser)
    args = parser.parse_args()
    logging_utils.update_logging(args)

    config = yaml.load(open(args.config), Loader=yaml.FullLoader)

    sample_name_map = ribo_utils.get_sample_name_map(config)

    res = parallel.apply_parallel_iter(config['riboseq_samples'].keys(),
                                       args.num_cpus,
                                       get_counts,
                                       sample_name_map,
                                       config,
                                       args)
    res_df = pd.DataFrame(res)

    if os.path.exists(args.out) and not args.overwrite:
        msg = "Output file {} already exists. Skipping.".format(args.out)
        logger.warning(msg)
    else:
        pandas_utils.write_df(res_df, args.out, create_path=True,
                              index=False, sep=',', header=True,
                              do_not_compress=False, quoting=csv.QUOTE_NONE)


if __name__ == '__main__':
    main()
