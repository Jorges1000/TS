#! /bin/sh
#
# Copyright by The HDF Group.
# Copyright by the Board of Trustees of the University of Illinois.
# All rights reserved.
#
# This file is part of HDF5.  The full HDF5 copyright notice, including
# terms governing use, modification, and redistribution, is contained in
# the files COPYING and Copyright.html.  COPYING can be found at the root
# of the source code distribution tree; Copyright.html can be found at the
# root level of an installed copy of the electronic HDF5 document set and
# is linked from the top-level documents page.  It can also be found at
# http://hdfgroup.org/HDF5/doc/Copyright.html.  If you do not have
# access to either file, you may request a copy from help@hdfgroup.org.
#
# Tests for the h5ls tool

TESTNAME=h5ls
EXIT_SUCCESS=0
EXIT_FAILURE=1

H5LS=h5ls               # The tool name
H5LS_BIN=`pwd`/$H5LS    # The path of the tool binary

CMP='cmp -s'
DIFF='diff -c'
NLINES=20			# Max. lines of output to display if test fails

WORDS_BIGENDIAN="no"

nerrors=0
verbose=yes
h5haveexitcode=yes	    # default is yes

# The build (current) directory might be different than the source directory.
if test -z "$srcdir"; then
    srcdir=.
fi
test -d ../testfiles || mkdir ../testfiles

# RUNSERIAL is used. Check if it can return exit code from executalbe correctly.
if [ -n "$RUNSERIAL_NOEXITCODE" ]; then
    echo "***Warning*** Serial Exit Code is not passed back to shell corretly."
    echo "***Warning*** Exit code checking is skipped."
    h5haveexitcode=no
fi

# Print a line-line message left justified in a field of 70 characters
# beginning with the word "Testing".
TESTING() {
    SPACES="                                                               "
    echo "Testing $* $SPACES" |cut -c1-70 |tr -d '\012'
}

# Some systems will dump some messages to stdout for various reasons.
# Remove them from the stdout result file.
# $1 is the file name of the file to be filtered.
# Cases of filter needed:
# 1. Sandia Red-Storm
#    yod always prints these two lines at the beginning.
#    LibLustre: NAL NID: 0004a605 (5)
#    Lustre: OBD class driver Build Version: 1, info@clusterfs.com
# 2. LANL Lambda
#    mpijob mirun -np always add an extra line at the end like:
#    P4 procgroup file is /users/acheng/.lsbatch/host10524.l82
STDOUT_FILTER() {
    result_file=$1
    tmp_file=/tmp/h5test_tmp_$$
    # Filter Sandia Red-Storm yod messages.
    cp $result_file $tmp_file
    sed -e '/^LibLustre:/d' -e '/^Lustre:/d' \
	< $tmp_file > $result_file
    # Filter LANL Lambda mpirun message.
    cp $result_file $tmp_file
    sed -e '/^P4 procgroup file is/d' \
	< $tmp_file > $result_file
    # cleanup
    rm -f $tmp_file
}

# Some systems will dump some messages to stderr for various reasons.
# Remove them from the stderr result file.
# $1 is the file name of the file to be filtered.
# Cases of filter needed:
# 1. MPE:
# In parallel mode and if MPE library is used, it prints the following
# two message lines whether the MPE tracing is used or not.
#    Writing logfile.
#    Finished writing logfile.
# 2. LANL MPI:
# The LANL MPI will print some messages like the following,
#    LA-MPI: *** mpirun (1.5.10)
#    LA-MPI: *** 3 process(es) on 2 host(s): 2*fln21 1*fln22
#    LA-MPI: *** libmpi (1.5.10)
#    LA-MPI: *** Copyright 2001-2004, ACL, Los Alamos National Laboratory
# 3. h5diff debug output:
#    Debug output all have prefix "h5diff debug: ".
# 4. AIX system prints messages like these when it is aborting:
#    ERROR: 0031-300  Forcing all remote tasks to exit due to exit code 1 in task 0
#    ERROR: 0031-250  task 4: Terminated
#    ERROR: 0031-250  task 3: Terminated
#    ERROR: 0031-250  task 2: Terminated
#    ERROR: 0031-250  task 1: Terminated
# 5. LLNL Blue-Gene mpirun prints messages like there when it exit non-zero:
#    <Apr 12 15:01:49.075658> BE_MPI (ERROR): The error message in the job record is as follows:
#    <Apr 12 15:01:49.075736> BE_MPI (ERROR):   "killed by exit(1) on node 0"


STDERR_FILTER() {
    result_file=$1
    tmp_file=/tmp/h5test_tmp_$$
    # Filter LLNL Blue-Gene error messages in both serial and parallel modes
    # since mpirun is used in both modes.
    cp $result_file $tmp_file
    sed -e '/ BE_MPI (ERROR): /d' \
	< $tmp_file > $result_file
    # Filter MPE messages
    if test -n "$pmode"; then
	cp $result_file $tmp_file
	sed -e '/^Writing logfile./d' -e '/^Finished writing logfile./d' \
	    < $tmp_file > $result_file
    fi
    # Filter LANL MPI messages
    # and LLNL srun messages
    # and AIX error messages
    if test -n "$pmode"; then
	cp $result_file $tmp_file
	sed -e '/^LA-MPI:/d' -e '/^srun:/d' -e '/^ERROR:/d' \
	    < $tmp_file > $result_file
    fi
    # Filter h5diff debug output
	cp $result_file $tmp_file
	sed -e '/^h5diff debug: /d' \
	    < $tmp_file > $result_file
    # clean up temporary files.
    rm -f $tmp_file
}

# Run a test and print PASS or *FAIL*. For now, if h5ls can complete
# with exit status 0, consider it pass. If a test fails then increment
# the `nerrors' global variable and (if $verbose is set) display up to $NLINS
# lines of the actual output from the tool test.  The actual output is not
# removed if $HDF5_NOCLEANUP has a non-zero value.
# Arguemnts:
# $1 -- actual output filename to use
# $2 and on -- argument for the h5ls tool
TOOLTEST() {
    expect="$srcdir/../testfiles/$1"
    actual="../testfiles/`basename $1 .ls`.out"
    actual_err="../testfiles/`basename $1 .ls`.err"
    actual_sav=${actual}-sav
    actual_err_sav=${actual_err}-sav
    shift
    retvalexpect=$1
    shift

    # Run test.
    # Stderr is included in stdout so that the diff can detect
    # any unexpected output from that stream too.
    TESTING $H5LS $@
    (
	echo "#############################"
	echo " output for '$H5LS $@'" 
	echo "#############################"
	cd $srcdir/../testfiles
        $RUNSERIAL $H5LS_BIN "$@"
    ) >$actual 2>$actual_err 
    
    exitcode=$?
    # save actual and actual_err in case they are needed later.
    cp $actual $actual_sav
    STDOUT_FILTER $actual
    cp $actual_err $actual_err_sav
    STDERR_FILTER $actual_err
    cat $actual_err >> $actual
    if [ $h5haveexitcode = 'yes' -a $exitcode -ne $retvalexpect ]; then
	echo "*FAILED*"
	nerrors="`expr $nerrors + 1`"
	if [ yes = "$verbose" ]; then
	    echo "test returned with exit code $exitcode"
	    echo "test output: (up to $NLINES lines)"
	    head -$NLINES $actual
	    echo "***end of test output***"
	    echo ""
	fi
    elif [ ! -f $expect ]; then
	# Create the expect file if it doesn't yet exist.
        echo " CREATED"
        cp $actual $expect
    elif $CMP $expect $actual; then
        echo " PASSED"
    else
        echo "*FAILED*"
	echo "    Expected result differs from actual result"
	nerrors="`expr $nerrors + 1`"
	test yes = "$verbose" && $DIFF $expect $actual |sed 's/^/    /'
    fi

    # Clean up output file
    if test -z "$HDF5_NOCLEANUP"; then
	rm -f $actual $actual_err $actual_sav $actual_err_sav
    fi
}

##############################################################################
##############################################################################
###			  T H E   T E S T S                                ###
##############################################################################
##############################################################################

# Toss in a bunch of tests.  Not sure if they are the right kinds.
# test the help syntax
TOOLTEST help-1.ls 0 -w80 -h
TOOLTEST help-2.ls 0 -w80 -help
TOOLTEST help-3.ls 0 -w80 -?

# test simple command
TOOLTEST tall-1.ls 0 -w80 tall.h5
TOOLTEST tall-2.ls 0 -w80 -r -d tall.h5
TOOLTEST tgroup.ls 0 -w80 tgroup.h5
TOOLTEST tgroup-3.ls 0 -w80 tgroup.h5/g1

# test for displaying groups
# The following combination of arguments is expected to return an error message
# and return value 1
TOOLTEST tgroup-1.ls 1 -w80 -r -g tgroup.h5
TOOLTEST tgroup-2.ls 0 -w80 -g tgroup.h5/g1

# test for files with groups that have long comments
TOOLTEST tgrp_comments.ls 0 -w80 -v -g tgrp_comments.h5/glongcomment

# test for displaying simple space datasets
TOOLTEST tdset-1.ls 0 -w80 -r -d tdset.h5

# test for displaying soft links
TOOLTEST tslink-1.ls 0 -w80 -r tslink.h5

# test for displaying more soft links with --follow-symlinks
TOOLTEST tsoftlinks-1.ls 0 --follow-symlinks tsoftlinks.h5
TOOLTEST tsoftlinks-2.ls 0 --follow-symlinks -r tsoftlinks.h5
TOOLTEST tsoftlinks-3.ls 0 --follow-symlinks tsoftlinks.h5/group1
TOOLTEST tsoftlinks-4.ls 0 --follow-symlinks -r tsoftlinks.h5/group1
TOOLTEST tsoftlinks-5.ls 0 --follow-symlinks tsoftlinks.h5/soft_dset1

# test for displaying external and user-defined links with --follow-symlinks
TOOLTEST textlink-1.ls 0 -w80 -r textlink.h5
TOOLTEST textlinksrc-1.ls 0 -w80 --follow-symlinks -r textlinksrc.h5
TOOLTEST textlinksrc-2.ls 0 -w80 --follow-symlinks -rv textlinksrc.h5/ext_link5
TOOLTEST textlinksrc-3.ls 0 -w80 --follow-symlinks -r textlinksrc.h5/ext_link1
TOOLTEST textlinksrc-4.ls 0 -w80 -r textlinksrc.h5
TOOLTEST textlinksrc-5.ls 0 -w80 -r textlinksrc.h5/ext_link1
TOOLTEST textlinksrc-6.ls 0 -w80 --follow-symlinks textlinksrc.h5
TOOLTEST textlinksrc-7.ls 0 -w80 --follow-symlinks textlinksrc.h5/ext_link1
TOOLTEST tudlink-1.ls 0 -w80 -r tudlink.h5

# test for displaying external links with -E
# the option -E will be depriciated but keep it for backward compatibility
TOOLTEST textlinksrc-1-old.ls 0 -w80 -Er textlinksrc.h5
TOOLTEST textlinksrc-2-old.ls 0 -w80 -Erv textlinksrc.h5/ext_link5
TOOLTEST textlinksrc-3-old.ls 0 -w80 -Er textlinksrc.h5/ext_link1
TOOLTEST textlinksrc-6-old.ls 0 -w80 -E textlinksrc.h5
TOOLTEST textlinksrc-7-old.ls 0 -w80 -E textlinksrc.h5/ext_link1

# tests for no-dangling-links 
# if this option is given on dangling link, h5ls should return exit code 1
# when used alone , expect to print out help and return exit code 1
TOOLTEST textlinksrc-nodangle-1.ls 1 -w80 --no-dangling-links textlinksrc.h5
# external dangling link - expected exit code 1
TOOLTEST textlinksrc-nodangle-2.ls 1 -w80 --follow-symlinks --no-dangling-links textlinksrc.h5
# soft dangling link - expected exit code 1
TOOLTEST tsoftlinks-nodangle-1.ls 1 -w80 --follow-symlinks --no-dangling-links tsoftlinks.h5
# when used file with no dangling links - expected exit code 0
TOOLTEST thlinks-nodangle-1.ls 0 -w80 --follow-symlinks --no-dangling-links thlink.h5


# tests for hard links
TOOLTEST thlink-1.ls 0 -w80 thlink.h5

# tests for compound data types
TOOLTEST tcomp-1.ls 0 -w80 -r -d tcompound.h5

#test for the nested compound type
TOOLTEST tnestcomp-1.ls 0 -w80 -r -d tnestedcomp.h5

TOOLTEST tnestcomp-2.ls 0 -w80 -r -d -S tnestedcomp.h5

TOOLTEST tnestcomp-3.ls 0 -w80 -r -d -l tnestedcomp.h5

TOOLTEST tnestcomp-4.ls 0 -w80 -r -d -l -S tnestedcomp.h5

# test for loop detection
TOOLTEST tloop-1.ls 0 -w80 -r -d tloop.h5

# test for string 
TOOLTEST tstr-1.ls 0 -w80 -r -d tstr.h5

# test test file created from lib SAF team
TOOLTEST tsaf.ls 0 -w80 -r -d tsaf.h5

# test for variable length data types
TOOLTEST tvldtypes1.ls 0 -w80 -r -d tvldtypes1.h5

# test for array data types
TOOLTEST tarray1.ls 0 -w80 -r -d tarray1.h5

# test for empty data
TOOLTEST tempty.ls 0 -w80 -d tempty.h5

# test for all dataset types written to attributes
# enable -S for avoiding printing NATIVE types
TOOLTEST tattr2.ls 0 -w80 -v -S tattr2.h5

# tests for error handling.
# test for non-existing file
TOOLTEST nosuchfile.ls 1 nosuchfile.h5

# test for variable length data types in verbose mode 
if test $WORDS_BIGENDIAN != "yes"; then
 TOOLTEST tvldtypes2le.ls 0 -v tvldtypes1.h5
else
 TOOLTEST tvldtypes2be.ls 0 -v tvldtypes1.h5
fi 


# test for dataset region references data types in verbose mode 
if test $WORDS_BIGENDIAN != "yes"; then
 TOOLTEST tdataregle.ls 0 -v tdatareg.h5
else
 TOOLTEST tdataregbe.ls 0 -v tdatareg.h5
fi 


if test $nerrors -eq 0 ; then
    echo "All $TESTNAME tests passed."
    exit $EXIT_SUCCESS
else
    echo "$TESTNAME tests failed with $nerrors errors."
    exit $EXIT_FAILURE
fi
