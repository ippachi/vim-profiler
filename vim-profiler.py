#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import sys
import subprocess
import re
import csv
import operator
import argparse
import collections

def to_list(cmd):
    if not isinstance(cmd, (list, tuple)):
        cmd = cmd.split(' ')
    return cmd

def get_exe(cmd):
    # FIXME: this assumes that the first word is the executable
    return to_list(cmd)[0]

def stdev(arr):
    """
    Compute the standard deviation.
    """
    if sys.version_info >= (3, 0):
        import statistics
        return statistics.pstdev(arr)
    else:
        # Dependency on NumPy
        try:
            import numpy
            return numpy.std(arr, axis=0)
        except ImportError:
            return 0.

class StartupData(object):
    """
    Data for (n)vim startup (timings etc.).
    """
    def __init__(self, cmd, log_filename):
        super(StartupData, self).__init__()
        self.cmd = cmd
        self.log_filename = log_filename
        self.times = dict()
        self.generate()

    def generate(self):
        """
        Generate startup data.
        """
        self.__run_vim()
        try:
            self.__load_times()
        except RuntimeError as e:
            print("\nNo plugin found. Exiting.")
            sys.exit()

    def __guess_plugin_dir(self, log_txt):
        """
        Try to guess the vim directory containing plugins.
        """
        candidates = list()
        user_dir = os.path.expanduser("~")

        # Get common plugin dir if any
        vim_subdirs="autoload|ftdetect|plugin|syntax"
        matches = re.findall("^\d+.\d+\s+\d+.\d+\s+\d+.\d+: sourcing (.+?)/(?:[^/]+/)(?:%s)/[^/]+" % vim_subdirs, log_txt, re.MULTILINE)
        for plugin_dir in matches:
            # Ignore system plugins
            if user_dir in plugin_dir:
                candidates.append(plugin_dir)

        if candidates:
            # FIXME: the directory containing vimrc could be returned as well
            return collections.Counter(candidates).most_common(1)[0][0]
        else:
            raise RuntimeError("no plugin found")

    def __load_times(self):
        """
        Load startup times for log file.
        """
        # Load log file and process it
        print("Loading and processing logs...", end="")
        with open(self.log_filename, 'r') as log:
            log_txt = log.read()

            # Try to guess the folder based on the logs themselves
            plugin_dir = self.__guess_plugin_dir(log_txt)

            matches = re.findall("^\d+.\d+\s+\d+.\d+\s+(\d+.\d+): sourcing %s/([^/]+)/" % plugin_dir, log_txt, re.MULTILINE)
            for res in matches:
                time = res[0]
                plugin = res[1]
                if plugin in self.times:
                    self.times[plugin] += float(time)
                else:
                    self.times[plugin] = float(time)
        print(" done.")
        print("Plugin directory: %s" % plugin_dir)

    def __run_vim(self):
        """
        Run vim/nvim to generate startup logs.
        """
        print("Running %s to generate startup logs..." % get_exe(self.cmd), end="")
        self.__clean_log()
        full_cmd = to_list(self.cmd) + ["--startuptime", self.log_filename, "-c", "q"]
        subprocess.call(full_cmd, shell=False)
        print(" done.")

    def __clean_log(self):
        """
        Clean log file.
        """
        if os.path.isfile(self.log_filename):
            os.remove(self.log_filename)

    def __del__(self):
        """
        Destructor taking care of clean up.
        """
        self.__clean_log()


class StartupAnalyzer(object):
    """
    Analyze startup times for (n)vim.
    """
    def __init__(self, param):
        super(StartupAnalyzer, self).__init__()
        self.runs = param.runs
        self.cmd = param.cmd
        self.raw_data = [StartupData(self.cmd, "vim_%i.log" % (i+1))
                         for i in range(self.runs)]
        self.data = self.process_data()

    def process_data(self):
        """
        Merge startup times for each plugin.
        """
        return {k: [d.times[k] for d in self.raw_data] for k in self.raw_data[0].times.keys()}

    def average_data(self):
        """
        Return average times for each plugin.
        """
        return {k: sum(v)/len(v) for k,v in self.data.items()}

    def stdev_data(self):
        """
        Return standard deviation for each plugin.
        """
        return {k: stdev(v) for k,v in self.data.items()}

    def plot(self):
        """
        Plot startup data.
        """
        import matplotlib
        # TODO: do not force matplotlib backend
        matplotlib.use('Qt5Agg')
        import pylab

        print("Plotting result...", end="")
        avg_data = self.average_data()
        avg_data = sorted(avg_data.items(), key=operator.itemgetter(1), reverse=False)
        err = self.stdev_data()
        sorted_err = [err[k] for k in zip(*avg_data)[0]]
        pylab.barh(range(len(avg_data)), zip(*avg_data)[1], xerr=sorted_err,
                   align='center', alpha=0.4)
        pylab.yticks(range(len(avg_data)), zip(*avg_data)[0])
        pylab.xlabel("Average startup time (ms)")
        pylab.ylabel("Plugins")
        pylab.show()
        print(" done.")

    def export(self, output_filename="result.csv"):
        """
        Write sorted result to file.
        """
        assert len(self.data) > 0
        print("Writing result to %s..." % output_filename, end="")
        with open(output_filename, 'w') as fp:
            writer = csv.writer(fp, delimiter='\t')
            # Compute average times
            avg_data = self.average_data()
            # Sort by average time
            for name, avg_time in sorted(avg_data.items(), key=operator.itemgetter(1), reverse=True):
                writer.writerow(["%.3f" % avg_time, name])
        print(" done.")

    def print_summary(self, n):
        """
        Print summary of startup times for plugins.
        """
        title = "Top %i plugins slowing %s's startup" % (n, get_exe(self.cmd))
        length = len(title)
        print(''.center(length, '='))
        print(title)
        print(''.center(length, '='))

        # Compute average times
        avg_data = self.average_data()
        # Sort by average time
        rank = 0
        for name, time in sorted(avg_data.items(), key=operator.itemgetter(1), reverse=True)[:n]:
            rank += 1
            print("%i\t%7.3f   %s" % (rank, time, name))

        print(''.center(length, '='))

def main():
    parser = argparse.ArgumentParser(description='Analyze startup times of vim/neovim plugins.')
    parser.add_argument("-o", dest="csv", type=str,
                        help="Export result to a csv file")
    parser.add_argument("-p", dest="plot", action='store_true',
                        help="Plot result as a bar chart")
    parser.add_argument("-n", dest="n", type=int, default=10,
                        help="Number of plugins to list in the summary")
    parser.add_argument("-r", dest="runs", type=int, default=1,
                        help="Number of runs (for average/standard deviation)")
    parser.add_argument(dest="cmd", nargs=argparse.REMAINDER, type=str,
                        help="vim/neovim executable or command")

    # Parse CLI arguments
    args = parser.parse_args()
    output_filename = args.csv
    n = args.n

    # Command (default = vim)
    if args.cmd == []:
        args.cmd = "vim"

    # Run analysis
    analyzer = StartupAnalyzer(args)
    if n > 0:
        analyzer.print_summary(n)
    if output_filename is not None:
        analyzer.export(output_filename)
    if args.plot:
        analyzer.plot()

if __name__ == "__main__":
    main()
