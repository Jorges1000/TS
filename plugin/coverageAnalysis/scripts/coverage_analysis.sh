#!/bin/bash
# Copyright (C) 2011 Ion Torrent Systems, Inc. All Rights Reserved

#--------- Begin command arg parsing ---------

CMD=`echo $0 | sed -e 's/^.*\///'`
DESCR="Create tsv and image files of mapped read coverage to a reference."
USAGE="USAGE:
  $CMD [options] <reference.fasta> <BAM file>"
OPTIONS="OPTIONS:
  -h --help Report usage and help.
  -l Log progress to STDERR.
  -d Ignore Duplicate reads.
  -u Include only Uniquely mapped reads (MAPQ > 1).
  -G <file> Genome file. Assumed to be <reference.fasta>.fai if not specified.
  -D <dirpath> Path to Directory where results are written.
  -O <file> Output file name for text data (per analysis). Use '-' for STDOUT. Default: 'summary.txt'.
  -B <file> Limit coverage to targets specified in this BED file.
  -P <file> Padded targets BED file for padded target coverage analysis.
  -0 Include 0x coverage in (binned) plots.
  -H <N> Set maximum coverage for Histogram plot to N. Default: 0.
      0 => Full bar plot (not linear)"

# should scan all args first for --X options
if [ "$1" = "--help" ]; then
    echo -e "$DESCR\n$USAGE\n$OPTIONS" >&2
    exit 0
fi

SHOWLOG=0
PLOT0=0
MAXCOV=0
BEDFILE=""
GENOME=""
WORKDIR="."
BINSIZE=0
OUTFILE="summary.txt"
PADBED=""
NONDUPREADS=0
UNIQUEREADS=0

while getopts "hldu0B:H:G:D:O:P:" opt
do
  case $opt in
    d) NONDUPREADS=1;;
    u) UNIQUEREADS=1;;
    l) SHOWLOG=1;;
    0) PLOT0=1;;
    B) BEDFILE=$OPTARG;;
    H) MAXCOV=$OPTARG;;
    G) GENOME=$OPTARG;;
    D) WORKDIR=$OPTARG;;
    O) OUTFILE=$OPTARG;;
    P) PADBED=$OPTARG;;
    h) echo -e "$DESCR\n$USAGE\n$OPTIONS" >&2
       exit 0;;
    \?) echo $USAGE >&2
        exit 1;;
  esac
done
shift `expr $OPTIND - 1`

if [ $# -ne 2 ]; then
  echo "$CMD: Invalid number of arguments." >&2
  echo -e "$USAGE\n$OPTIONS" >&2
  exit 1
fi

REFERENCE=$1
BAMFILE=$2

if [ -z "$GENOME" ]; then
  GENOME="$REFERENCE.fai"
fi
if [ "$OUTFILE" == "-" ]; then
  OUTFILE=""
fi

#--------- End command arg parsing ---------

RUNPTH=`readlink -n -f $0`
RUNDIR=`dirname $RUNPTH`
#echo -e "RUNDIR=$RUNDIR\n" >&2

# Check environment

BAMROOT=`echo $BAMFILE | sed -e 's/^.*\///'`
BAMNAME=`echo $BAMROOT | sed -e 's/\.[^.]*$//'`

if [ $SHOWLOG -eq 1 ]; then
  echo "$CMD BEGIN:" `date` >&2
  echo "REFERENCE: $REFERENCE" >&2
  echo "MAPPINGS:  $BAMROOT" >&2
  echo "GENOME:    $GENOME" >&2
  if [ -n "$BEDFILE" ]; then
    echo "TARGETS:   $BEDFILE" >&2
  fi
  echo "WORKDIR:   $WORKDIR" >&2
  if [ -n "$OUTFILE" ];then
    echo "TEXT OUT:  $OUTFILE" >&2
  else
    echo "TEXT OUT:  <STDOUT>" >&2
  fi
  echo >&2
fi

if ! [ -d "$RUNDIR" ]; then
  echo "ERROR: Executables directory does not exist at $RUNDIR" >&2
  exit 1
elif ! [ -d "$WORKDIR" ]; then
  echo "ERROR: Output work directory does not exist at $WORKDIR" >&2
  exit 1
elif ! [ -f "$GENOME" ]; then
  echo "ERROR: Genome (.fai) file does not exist at $GENOME" >&2
  exit 1
elif ! [ -f "$REFERENCE" ]; then
  echo "ERROR: Reference sequence (fasta) file does not exist at $REFERENCE" >&2
  exit 1
elif ! [ -f "$BAMFILE" ]; then
  echo "ERROR: Mapped reads (bam) file does not exist at $BAMFILE" >&2
  exit 1
elif [ -n "$BEDFILE" -a ! -f "$BEDFILE" ]; then
  echo "ERROR: Reference targets (bed) file does not exist at $BEDFILE" >&2
  exit 1
elif [ -n "$PADBED" -a ! -f "$PADBED" ]; then
  echo "ERROR: Padded reference targets (bed) file does not exist at $PADBED" >&2
  exit 1;
fi

# Get absolute file paths to avoid link issues in HTML
WORKDIR=`readlink -n -f "$WORKDIR"`
REFERENCE=`readlink -n -f "$REFERENCE"`
#BAMFILE=`readlink -n -f "$BAMFILE"`
GENOME=`readlink -n -f "$GENOME"`

ROOTNAME="$WORKDIR/$BAMNAME"
if [ -n "$OUTFILE" ];then
  touch "$WORKDIR/$OUTFILE"
  OUTFILE=">> \"$WORKDIR/$OUTFILE\""
fi

# delete old run data
rm -f "$WORKDIR"/*

PASSFILTER=""
if [ $NONDUPREADS -eq 1 ];then
  PASSFILTER="-d"
fi
if [ $UNIQUEREADS -eq 1 ];then
  PASSFILTER="$PASSFILTER -u"
fi

############

COVOVR_XLS=$ROOTNAME.covoverview.xls

if [ -n "$BEDFILE" ]; then
  COVERAGE_ANALYSIS="perl $RUNDIR/cover_over.pl $PASSFILTER -B \"$BEDFILE\" -G \"$GENOME\" \"$BAMFILE\" > \"$COVOVR_XLS\""
else
  COVERAGE_ANALYSIS="perl $RUNDIR/cover_over.pl $PASSFILTER -G \"$GENOME\" \"$BAMFILE\" > \"$COVOVR_XLS\""
fi

if [ $SHOWLOG -eq 1 ]; then
  echo "Calculating effective reference coverage overview..." >&2
fi
eval "$COVERAGE_ANALYSIS" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: cover_over.pl failed." >&2
  echo "\$ $COVERAGE_ANALYSIS" >&2
  exit 1;
fi

if [ "$SHOWLOG" -eq 1 ]; then
  echo "> $COVOVR_XLS" >&2
fi

CHRCNT_XLS=$ROOTNAME.coverage_by_chrom.xls
CHRMAP_XLS=$ROOTNAME.coverage_map_by_chrom.xls

# Note: supplying genome is useful for getting overriding the chromosome order in the bed file
if [ -n "$BEDFILE" ]; then
  COVERAGE_ANALYSIS="perl $RUNDIR/chart_by_chrom.pl $PASSFILTER -o -B \"$BEDFILE\" -F \"$CHRMAP_XLS\" -G \"$GENOME\" \"$BAMFILE\" \"$CHRCNT_XLS\""
else
  COVERAGE_ANALYSIS="perl $RUNDIR/chart_by_chrom.pl $PASSFILTER -o -F \"$CHRMAP_XLS\" -G \"$GENOME\" \"$BAMFILE\" \"$CHRCNT_XLS\""
fi

if [ $SHOWLOG -eq 1 ]; then
  echo "Calculating read distribution by chromosome..." >&2
fi
eval "$COVERAGE_ANALYSIS $OUTFILE" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: chart_by_chrom.pl failed." >&2
  echo "\$ $COVERAGE_ANALYSIS $OUTFILE" >&2
  exit 1;
fi
if [ $SHOWLOG -eq 1 ]; then
  echo "> $CHRCNT_XLS" >&2
  echo "> $CHRMAP_XLS" >&2
fi

CHRPAD_XLS=$ROOTNAME.coverage_by_chrom_padded_target.xls
if [ -n "$PADBED" ]; then
  COVERAGE_ANALYSIS="perl $RUNDIR/chart_by_chrom.pl $PASSFILTER -p -B \"$PADBED\" -G \"$GENOME\" \"$BAMFILE\" \"$CHRPAD_XLS\""
  eval "$COVERAGE_ANALYSIS $OUTFILE" >&2
  if [ $? -ne 0 ]; then
    echo -e "\nERROR: chart_by_chrom.pl failed for padded targets." >&2
    echo "\$ $COVERAGE_ANALYSIS $OUTFILE" >&2
    exit 1;
  fi
  if [ $SHOWLOG -eq 1 ]; then
    echo "> $CHRPAD_XLS" >&2
  fi
fi
if [ $SHOWLOG -eq 1 ]; then
  echo "Chromosome coverage analysis done:" `date` >&2
fi

############

SAMOPT=""
if [ $NONDUPREADS -eq 0 ];then
  # explicit option to ignore filtering of non-duplicates
  SAMOPT="-F 0x304"
fi
if [ $UNIQUEREADS -eq 1 ];then
  SAMOPT="$SAMOPT -Q 1"
fi

FPILEUP="$ROOTNAME.starts.pileup"
if [ -n "$BEDFILE" ]; then
  PILEUP_STARTS="samtools depth $SAMOPT -b \"$BEDFILE\" \"$BAMFILE\" 2> /dev/null > \"$FPILEUP\""
else
  PILEUP_STARTS="samtools depth $SAMOPT \"$BAMFILE\" 2> /dev/null > \"$FPILEUP\""
fi

if [ $SHOWLOG -eq 1 ]; then
  echo -e "\nCounting base read depths..." >&2
  echo "\$ $PILEUP_STARTS" >&2
fi
eval "$PILEUP_STARTS" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: samtools depth failed." >&2
  echo "\$ $PILEUP_STARTS" >&2
  exit 1;
fi
if [ $SHOWLOG -eq 1 ]; then
  echo "Base read depth counting done:" `date` >&2
fi

############

TARGCOV_XLS=$ROOTNAME.fine_coverage.xls

if [ -n "$BEDFILE" ]; then
  FINE_COVERAGE_ANALYSIS="perl $RUNDIR/bed_covers.pl -G \"$GENOME\" \"$FPILEUP\" \"$BEDFILE\" > \"$TARGCOV_XLS\""
  if [ $SHOWLOG -eq 1 ]; then
    echo -e "\nCreating individual targets coverage..." >&2
  fi
  eval "$FINE_COVERAGE_ANALYSIS" >&2
  if [ $? -ne 0 ]; then
    echo -e "\nERROR: bed_covers.pl failed." >&2
    echo "\$ $FINE_COVERAGE_ANALYSIS" >&2
    exit 1;
  fi
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $TARGCOV_XLS >&2
    echo "Individual targets coverage done:" `date` >&2
  fi
fi

############

OUTCOV_XLS=$ROOTNAME.coverage.xls
OUTCOV_BIN_XLS=$ROOTNAME.coverage_binned.xls

if [ $SHOWLOG -eq 1 ]; then
  echo -e "\nCalculating coverage..." >&2
fi

if [ -n "$BEDFILE" ]; then
  gnm_size=`awk 'BEGIN {gs = 0} {gs += $3-$2} END {printf "%.0f",gs+0}' "$BEDFILE"`
else
  gnm_size=`awk 'BEGIN {gs = 0} {gs += $2} END {printf "%.0f",gs+0}' "$GENOME"`
fi

base_reads=0
if [ -n "$BEDFILE" ]; then
  # find total number of mapped bases for % on-target
  base_reads=`samtools depth "$BAMFILE" | awk '{c+=$3} END {printf "%.0f",c+0}'`
else
  # should always result in 100% where there are no targets
  base_reads=`awk '{c+=$3} END {printf "%.0f",c+0}' "$FPILEUP"`
fi

COVERAGE_ANALYSIS="awk -f $RUNDIR/coverage_analysis.awk -v basereads=$base_reads -v genome=$gnm_size -v outfile=\"$OUTCOV_BIN_XLS\" -v x1cover=\"$OUTCOV_XLS\" -v plot0x=$PLOT0 -v showlevels=$MAXCOV -v binsize=$BINSIZE \"$FPILEUP\""

if [ $SHOWLOG -eq 1 ]; then
echo "\$ $COVERAGE_ANALYSIS" >&2
fi
eval "$COVERAGE_ANALYSIS $OUTFILE" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: awk command failed." >&2
  echo "\$ $COVERAGE_ANALYSIS $OUTFILE" >&2
  exit 1;
fi
if [ $SHOWLOG -eq 1 ]; then
  echo ">" $OUTCOV_XLS >&2
  echo ">" $OUTCOV_BIN_XLS >&2
  echo "Coverage analysis done:" `date` >&2
fi

############

if [ $SHOWLOG -eq 1 ]; then
  echo -e "\nCreating coverage plots..." >&2
fi
plotError=0

COVOVR_PNG=$ROOTNAME.covoverview.png
PLOTCMD="R --no-save --slave --vanilla --args \"$COVOVR_XLS\" \"$COVOVR_PNG\" < $RUNDIR/plot_overview.R"
eval "$PLOTCMD" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: plot_overview.R failed." >&2
  plotError=1
else
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $COVOVR_PNG >&2
  fi
fi

OUTCOV_PNG=$ROOTNAME.coverage.png
PLOTCMD="R --no-save --slave --vanilla --args \"$OUTCOV_XLS\" \"$OUTCOV_PNG\" < $RUNDIR/plot_coverage.R"
eval "$PLOTCMD" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: plot_coverage.R failed." >&2
  plotError=1
else
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $OUTCOV_PNG >&2
  fi
fi

OUTCOV_PNG=$ROOTNAME.coverage_normalized.png
PLOTCMD="R --no-save --slave --vanilla --args \"$OUTCOV_XLS\" \"$OUTCOV_PNG\" < $RUNDIR/plot_normalized_coverage.R"
eval "$PLOTCMD" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: plot_normalized_coverage.R failed." >&2
  plotError=1
else
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $OUTCOV_PNG >&2
  fi
fi

OUTCOV_PNG=$ROOTNAME.coverage_binned.png
PLOTCMD="R --no-save --slave --vanilla --args \"$OUTCOV_BIN_XLS\" \"$OUTCOV_PNG\" 0 < $RUNDIR/plot_binned_coverage.R"
eval "$PLOTCMD" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: plot_binned_coverage.R failed for binned read coverage." >&2
  plotError=1
else
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $OUTCOV_PNG >&2
  fi
fi

# disabled as plot is not considered of use at this time
#OUTCOV_PNG=$ROOTNAME.coverage_distribution.png
#PLOTCMD="R --no-save --slave --vanilla --args \"$OUTCOV_BIN_XLS\" \"$OUTCOV_PNG\" 1 < $RUNDIR/plot_binned_coverage.R"
#eval "$PLOTCMD" >&2
#if [ $? -ne 0 ]; then
#  echo -e "\nERROR: plot_binned_coverage.R failed for binned read distribution." >&2
#  plotError=1
#else
#  if [ $SHOWLOG -eq 1 ]; then
#    echo ">" $OUTCOV_PNG >&2
#  fi
#fi

OUTCOV_PNG=$ROOTNAME.coverage_onoff_target.png
PLOTCMD="R --no-save --slave --vanilla --args \"$CHRCNT_XLS\" \"$OUTCOV_PNG\" < $RUNDIR/plot_onoff_target.R"
eval "$PLOTCMD" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: plot_onoff_target.R failed." >&2
  plotError=1
else
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $OUTCOV_PNG >&2
  fi
fi

if [ -n "$PADBED" ]; then
  OUTCOV_PNG=$ROOTNAME.coverage_onoff_padded_target.png
  PLOTCMD="R --no-save --slave --vanilla --args \"$CHRPAD_XLS\" \"$OUTCOV_PNG\" < $RUNDIR/plot_onoff_padded_target.R"
  eval "$PLOTCMD" >&2
  if [ $? -ne 0 ]; then
    echo -e "\nERROR: plot_onoff_padded_target.R failed." >&2
    plotError=1
  else
    if [ $SHOWLOG -eq 1 ]; then
      echo ">" $OUTCOV_PNG >&2
    fi
  fi
fi
 
if [ -n "$BEDFILE" ]; then
  CHRMAP_PNG=$ROOTNAME.coverage_on_target.png
  PLOTCMD="R --no-save --slave --vanilla --args \"$TARGCOV_XLS\" \"$CHRMAP_PNG\" < $RUNDIR/plot_on_target.R"
  eval "$PLOTCMD" >&2
  if [ $? -ne 0 ]; then
    echo -e "\nERROR: plot_on_target.R failed." >&2
    plotError=1
  else
    if [ $SHOWLOG -eq 1 ]; then
      echo ">" $CHRMAP_PNG >&2
    fi
  fi
fi

CHRMAP_PNG=$ROOTNAME.coverage_map_onoff_target.png
PLOTCMD="R --no-save --slave --vanilla --args \"$CHRMAP_XLS\" \"$CHRMAP_PNG\" < $RUNDIR/plot_map_onoff_target.R"
eval "$PLOTCMD" >&2
if [ $? -ne 0 ]; then
  echo -e "\nERROR: plot_map_onoff_target.R failed." >&2
  plotError=1
else
  if [ $SHOWLOG -eq 1 ]; then
    echo ">" $CHRMAP_PNG >&2
  fi
fi

rm -f "$FPILEUP"
#if [ $plotError -eq 1 ]; then
#  exit 1;
#fi
if [ $SHOWLOG -eq 1 ]; then
  echo -e "\n$CMD END:" `date` >&2
fi

