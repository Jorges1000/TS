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
# Tests for the h5dump tool

# Determine which filters are available
USE_FILTER_SZIP="no"
USE_FILTER_DEFLATE="yes"
USE_FILTER_SHUFFLE="yes"
USE_FILTER_FLETCHER32="yes"
USE_FILTER_NBIT="yes"
USE_FILTER_SCALEOFFSET="yes"

# Determine if H5dump packed bits feature is included
Have_Packed_Bits="yes"

TESTNAME=h5dump
EXIT_SUCCESS=0
EXIT_FAILURE=1

DUMPER=h5dump                     # The tool name
DUMPER_BIN=`pwd`/$DUMPER          # The path of the tool binary
TESTDIR=`pwd`/../testfiles

H5DIFF=../h5diff/h5diff           # The h5diff tool name 
H5DIFF_BIN=`pwd`/$H5DIFF          # The path of the h5diff  tool binary

H5IMPORT=../h5import/h5import     # The h5import tool name 
H5IMPORT_BIN=`pwd`/$H5IMPORT      # The path of the h5import  tool binary


CMP='cmp -s'
DIFF='diff -c'

nerrors=0
verbose=yes

# The build (current) directory might be different than the source directory.
if test -z "$srcdir"; then
   srcdir=.
fi

test -d $TESTDIR || mkdir $TESTDIR

# Print a line-line message left justified in a field of 70 characters
# beginning with the word "Testing".
#
TESTING() {
   SPACES="                                                               "
   echo "Testing $* $SPACES" | cut -c1-70 | tr -d '\012'
}

# Run a test and print PASS or *FAIL*.  If a test fails then increment
# the `nerrors' global variable and (if $verbose is set) display the
# difference between the actual output and the expected output. The
# expected output is given as the first argument to this function and
# the actual output file is calculated by replacing the `.ddl' with
# `.out'.  The actual output is not removed if $HDF5_NOCLEANUP has a
# non-zero value.
#
TOOLTEST() {
    expect="$srcdir/../testfiles/$1"
    actual="../testfiles/`basename $1 .ddl`.out"
    actual_err="../testfiles/`basename $1 .ddl`.err"
    shift

    # Run test.
    TESTING $DUMPER $@
    (
      echo "#############################"
      echo "Expected output for '$DUMPER $@'" 
      echo "#############################"
	  cd $srcdir/../testfiles
  	  $RUNSERIAL $DUMPER_BIN $@
    ) >$actual 2>$actual_err
    cat $actual_err >> $actual

	if [ ! -f $expect ]; then
    # Create the expect file if it doesn't yet exist.
     echo " CREATED"
     cp $actual $expect
    elif $CMP $expect $actual; then
     echo " PASSED"
    else
     echo "*FAILED*"
     echo "    Expected result (*.ddl) differs from actual result (*.out)"
	 nerrors="`expr $nerrors + 1`"
	 test yes = "$verbose" && $DIFF $expect $actual |sed 's/^/    /'
    fi

    # Clean up output file
    if test -z "$HDF5_NOCLEANUP"; then
	 rm -f $actual $actual_err
    fi

}


# same as TOOLTEST but does not print the header Expected output
# used for the binary tests that expect a full path in -o
TOOLTEST1() {

    expect="$srcdir/../testfiles/$1"
    actual="../testfiles/`basename $1 .ddl`.out"
    actual_err="../testfiles/`basename $1 .ddl`.err"
    shift

    # Run test.
    TESTING $DUMPER $@
    (
      
	  cd $srcdir/../testfiles
  	  $RUNSERIAL $DUMPER_BIN $@
    ) >$actual 2>$actual_err
    cat $actual_err >> $actual

	if [ ! -f $expect ]; then
    # Create the expect file if it doesn't yet exist.
     echo " CREATED"
     cp $actual $expect
    elif $CMP $expect $actual; then
     echo " PASSED"
    else
     echo "*FAILED*"
     echo "    Expected result (*.ddl) differs from actual result (*.out)"
	 nerrors="`expr $nerrors + 1`"
	 test yes = "$verbose" && $DIFF $expect $actual |sed 's/^/    /'
    fi

    # Clean up output file
    if test -z "$HDF5_NOCLEANUP"; then
	 rm -f $actual $actual_err
    fi

}

# same as TOOLTEST1 but compares generated file to expected output
#                   and compares the generated data file to the expected data file
# used for the binary tests that expect a full path in -o without -b
TOOLTEST2() {

    expectdata="$srcdir/../testfiles/$1"
    expect="$srcdir/../testfiles/`basename $1 .exp`.ddl"
    actualdata="../testfiles/`basename $1 .exp`.txt"
    actual="../testfiles/`basename $1 .exp`.out"
    actual_err="../testfiles/`basename $1 .exp`.err"
    shift

    # Run test.
    TESTING $DUMPER $@
    (
      
      cd $srcdir/../testfiles
      $RUNSERIAL $DUMPER_BIN $@
    ) >$actual 2>$actual_err
    cat $actual_err >> $actual

    if [ ! -f $expect ]; then
    # Create the expect file if it doesn't yet exist.
     echo " CREATED"
     cp $actual $expect
    elif $CMP $expect $actual; then
      if [ ! -f $expectdata ]; then
      # Create the expect data file if it doesn't yet exist.
        echo " CREATED"
        cp $actualdata $expectdata
      elif $CMP $expectdata $actualdata; then
        echo " PASSED"
      else
        echo "*FAILED*"
        echo "    Expected datafile (*.exp) differs from actual datafile (*.txt)"
        nerrors="`expr $nerrors + 1`"
        test yes = "$verbose" && $DIFF $expectdata $actualdata |sed 's/^/    /'
      fi
    else
     echo "*FAILED*"
     echo "    Expected result (*.ddl) differs from actual result (*.out)"
     nerrors="`expr $nerrors + 1`"
     test yes = "$verbose" && $DIFF $expect $actual |sed 's/^/    /'
    fi
    
    # Clean up output file
    if test -z "$HDF5_NOCLEANUP"; then
     rm -f $actual $actualdata $actual_err
    fi

}

# same as TOOLTEST but filters error stack outp
# Extract file name, line number, version and thread IDs because they may be different
TOOLTEST3() {

    expect="$srcdir/../testfiles/$1"
    actual="../testfiles/`basename $1 .ddl`.out"
    actual_err="../testfiles/`basename $1 .ddl`.err"
    actual_ext="../testfiles/`basename $1 .ddl`.ext"
    shift

    # Run test.
    TESTING $DUMPER $@
    (
      echo "#############################"
      echo "Expected output for '$DUMPER $@'" 
      echo "#############################"
      cd $srcdir/../testfiles
      $RUNSERIAL $DUMPER_BIN $@
    ) >$actual 2>$actual_err

    # Extract file name, line number, version and thread IDs because they may be different
    sed -e 's/thread [0-9]*/thread (IDs)/' -e 's/: .*\.c /: (file name) /' \
        -e 's/line [0-9]*/line (number)/' \
        -e 's/v[1-9]*\.[0-9]*\./version (number)\./' \
        -e 's/[1-9]*\.[0-9]*\.[0-9]*[^)]*/version (number)/' \
        -e 's/H5Eget_auto[1-2]*/H5Eget_auto(1 or 2)/' \
        -e 's/H5Eset_auto[1-2]*/H5Eset_auto(1 or 2)/' \
     $actual_err > $actual_ext
    cat $actual_ext >> $actual

    if [ ! -f $expect ]; then
    # Create the expect file if it doesn't yet exist.
     echo " CREATED"
     cp $actual $expect
    elif $CMP $expect $actual; then
     echo " PASSED"
    else
     echo "*FAILED*"
     echo "    Expected result (*.ddl) differs from actual result (*.out)"
     nerrors="`expr $nerrors + 1`"
     test yes = "$verbose" && $DIFF $expect $actual |sed 's/^/    /'
    fi

    # Clean up output file
    if test -z "$HDF5_NOCLEANUP"; then
     rm -f $actual $actual_err
    fi

}

# Print a "SKIP" message
SKIP() {
	 TESTING $DUMPER $@
	  echo  " -SKIP-"
}
  
# Print a line-line message left justified in a field of 70 characters
#
PRINT_H5DIFF() {
 SPACES="                                                               "
 echo " Running h5diff $* $SPACES" | cut -c1-70 | tr -d '\012'
}


# Call the h5diff tool
#
DIFFTEST() 
{
    PRINT_H5DIFF  $@
    (
	cd $srcdir/../testfiles
	$RUNSERIAL $H5DIFF_BIN "$@" -q
    )
    RET=$?
    if [ $RET != 0 ] ; then
         echo "*FAILED*"
         nerrors="`expr $nerrors + 1`"
    else
         echo " PASSED"
    fi
        
}

# Print a line-line message left justified in a field of 70 characters
# beginning with the word "Verifying".
#
PRINT_H5IMPORT() {
 SPACES="                                                               "
 echo " Running h5import $* $SPACES" | cut -c1-70 | tr -d '\012'
}

# Call the h5import tool
#
IMPORTTEST() 
{
    # remove the output hdf5 file if it exists
    hdf5_file="$srcdir/../testfiles/$5"
    if [ -f $hdf5_file ]; then
     rm -f $hdf5_file
    fi

    PRINT_H5IMPORT  $@
    (
	cd $srcdir/../testfiles
	$RUNSERIAL $H5IMPORT_BIN "$@" 
    )
    RET=$?
    if [ $RET != 0 ] ; then
         echo "*FAILED*"
         nerrors="`expr $nerrors + 1`"
    else
         echo " PASSED"
    fi
        
}


##############################################################################
##############################################################################
###			  T H E   T E S T S                                            ###
##############################################################################
##############################################################################

# test for signed/unsigned datasets
TOOLTEST packedbits.ddl packedbits.h5
# test for displaying groups
TOOLTEST tgroup-1.ddl tgroup.h5
# test for displaying the selected groups
TOOLTEST tgroup-2.ddl --group=/g2 --group / -g /y tgroup.h5

# test for displaying simple space datasets
TOOLTEST tdset-1.ddl tdset.h5
# test for displaying selected datasets
TOOLTEST tdset-2.ddl -H -d dset1 -d /dset2 --dataset=dset3 tdset.h5

# test for displaying attributes
TOOLTEST tattr-1.ddl tattr.h5
# test for displaying the selected attributes of string type and scalar space
TOOLTEST tattr-2.ddl -a /attr1 --attribute /attr4 --attribute=/attr5 tattr.h5
# test for header and error messages
TOOLTEST tattr-3.ddl --header -a /attr2 --attribute=/attr tattr.h5
# test for displaying attributes in shared datatype (also in group and dataset)
TOOLTEST tnamed_dtype_attr.ddl tnamed_dtype_attr.h5

# test for displaying soft links and user-defined links
TOOLTEST tslink-1.ddl tslink.h5
TOOLTEST tudlink-1.ddl tudlink.h5
# test for displaying the selected link
TOOLTEST tslink-2.ddl -l slink2 tslink.h5
TOOLTEST tudlink-2.ddl -l udlink2 tudlink.h5

# tests for hard links
TOOLTEST thlink-1.ddl thlink.h5
TOOLTEST thlink-2.ddl -d /g1/dset2 --dataset /dset1 --dataset=/g1/g1.1/dset3 thlink.h5
TOOLTEST thlink-3.ddl -d /g1/g1.1/dset3 --dataset /g1/dset2 --dataset=/dset1 thlink.h5
TOOLTEST thlink-4.ddl -g /g1 thlink.h5
TOOLTEST thlink-5.ddl -d /dset1 -g /g2 -d /g1/dset2 thlink.h5

# tests for compound data types
TOOLTEST tcomp-1.ddl tcompound.h5
# test for named data types
TOOLTEST tcomp-2.ddl -t /type1 --datatype /type2 --datatype=/group1/type3 tcompound.h5
# test for unamed type 
TOOLTEST tcomp-3.ddl -t /#6632 -g /group2 tcompound.h5
# test complicated compound datatype
TOOLTEST tcomp-4.ddl tcompound_complex.h5

#test for the nested compound type
TOOLTEST tnestcomp-1.ddl tnestedcomp.h5

# test for options
TOOLTEST tall-1.ddl tall.h5
TOOLTEST tall-2.ddl --header -g /g1/g1.1 -a attr2 tall.h5
TOOLTEST tall-3.ddl -d /g2/dset2.1 -l /g1/g1.2/g1.2.1/slink tall.h5

# test for loop detection
TOOLTEST tloop-1.ddl tloop.h5

# test for string 
TOOLTEST tstr-1.ddl tstr.h5
TOOLTEST tstr-2.ddl tstr2.h5

# test for file created by Lib SAF team
TOOLTEST tsaf.ddl tsaf.h5

# test for file with variable length data
TOOLTEST tvldtypes1.ddl tvldtypes1.h5
TOOLTEST tvldtypes2.ddl tvldtypes2.h5
TOOLTEST tvldtypes3.ddl tvldtypes3.h5
TOOLTEST tvldtypes4.ddl tvldtypes4.h5
TOOLTEST tvldtypes5.ddl tvldtypes5.h5

#test for file with variable length string data
TOOLTEST tvlstr.ddl tvlstr.h5

# test for files with array data
TOOLTEST tarray1.ddl tarray1.h5
# # added for bug# 2092 - tarray1_big.h
TOOLTEST tarray1_big.ddl -R tarray1_big.h5
TOOLTEST tarray2.ddl tarray2.h5
TOOLTEST tarray3.ddl tarray3.h5
TOOLTEST tarray4.ddl tarray4.h5
TOOLTEST tarray5.ddl tarray5.h5
TOOLTEST tarray6.ddl tarray6.h5
TOOLTEST tarray7.ddl tarray7.h5
TOOLTEST tarray8.ddl tarray8.h5

# test for files with empty data
TOOLTEST tempty.ddl tempty.h5

# test for files with groups that have comments
TOOLTEST tgrp_comments.ddl tgrp_comments.h5

# test the --filedriver flag
TOOLTEST tsplit_file.ddl --filedriver=split tsplit_file
TOOLTEST tfamily.ddl --filedriver=family tfamily%05d.h5
TOOLTEST tmulti.ddl --filedriver=multi tmulti

# test for files with group names which reach > 1024 bytes in size
TOOLTEST tlarge_objname.ddl -w157 tlarge_objname.h5

# test '-A' to suppress data but print attr's
TOOLTEST tall-2A.ddl -A tall.h5

# test '-r' to print attributes in ASCII instead of decimal
TOOLTEST tall-2B.ddl -A -r tall.h5

# test Subsetting
TOOLTEST tall-4s.ddl --dataset=/g1/g1.1/dset1.1.1 --start=1,1 --stride=2,3 --count=3,2 --block=1,1 tall.h5
TOOLTEST tall-5s.ddl -d "/g1/g1.1/dset1.1.2[0;2;10;]" tall.h5
TOOLTEST tdset-3s.ddl -d "/dset1[1,1;;;]" tdset.h5


# test printing characters in ASCII instead of decimal
TOOLTEST tchar1.ddl -r tchar.h5

# test failure handling
# Missing file name
if test "$Have_Packed_Bits" = "yes"; then
    TOOLTEST tnofilename-with-packed-bits.ddl
else
    TOOLTEST tnofilename.ddl
fi

# rev. 2004

# tests for super block
TOOLTEST tboot1.ddl -H -B -d dset tfcontents1.h5
TOOLTEST tboot2.ddl -B tfcontents2.h5

# test -p with a non existing dataset
TOOLTEST tperror.ddl -p -d bogus tfcontents1.h5

# test for file contents
TOOLTEST tcontents.ddl -n tfcontents1.h5

# tests for storage layout
# compact
TOOLTEST tcompact.ddl -H -p -d compact tfilters.h5
# contiguous
TOOLTEST tcontiguos.ddl -H -p -d contiguous tfilters.h5
# chunked
TOOLTEST tchunked.ddl -H -p -d chunked tfilters.h5
# external 
TOOLTEST texternal.ddl -H -p -d external tfilters.h5

# fill values
TOOLTEST tfill.ddl -p tfvalues.h5

# several datatype, with references , print path
TOOLTEST treference.ddl  tattr2.h5

# escape/not escape non printable characters
TOOLTEST tstringe.ddl -e tstr3.h5
TOOLTEST tstring.ddl tstr3.h5
# char data as ASCII with non escape
TOOLTEST tstring2.ddl -r -d str4 tstr3.h5

# array indices print/not print
TOOLTEST tindicesyes.ddl taindices.h5
TOOLTEST tindicesno.ddl -y taindices.h5

########## array indices with subsetting
# 1D case
TOOLTEST tindicessub1.ddl -d 1d -s 1 -S 10 -c 2  -k 3 taindices.h5

# 2D case
TOOLTEST tindicessub2.ddl -d 2d -s 1,2  -S 3,3 -c 3,2 -k 2,2 taindices.h5

# 3D case
TOOLTEST tindicessub3.ddl -d 3d -s 0,1,2 -S 1,3,3 -c 2,2,2  -k 1,2,2  taindices.h5

# 4D case
TOOLTEST tindicessub4.ddl -d 4d -s 0,0,1,2  -c 2,2,3,2 -S 1,1,3,3 -k 1,1,2,2  taindices.h5

#Exceed the dimensions for subsetting
TOOLTEST1 texceedsubstart.ddl -d 1d -s 1,3 taindices.h5
TOOLTEST1 texceedsubcount.ddl -d 1d -c 1,3 taindices.h5
TOOLTEST1 texceedsubstride.ddl -d 1d -S 1,3 taindices.h5
TOOLTEST1 texceedsubblock.ddl -d 1d -k 1,3 taindices.h5


# tests for filters
# SZIP
option="-H -p -d szip tfilters.h5"
if test $USE_FILTER_SZIP != "yes"; then
 SKIP $option
else
TOOLTEST tszip.ddl $option
fi
# deflate
option="-H -p -d deflate tfilters.h5"
if test $USE_FILTER_DEFLATE != "yes"; then
 SKIP $option
else
 TOOLTEST tdeflate.ddl $option
fi
# shuffle
option="-H -p -d shuffle tfilters.h5"
if test $USE_FILTER_SHUFFLE != "yes"; then
 SKIP $option
else
 TOOLTEST tshuffle.ddl $option
fi
# fletcher32
option="-H -p -d fletcher32  tfilters.h5"
if test $USE_FILTER_FLETCHER32 != "yes"; then
 SKIP $option
else
 TOOLTEST tfletcher32.ddl $option
fi
# nbit
option="-H -p -d nbit  tfilters.h5"
if test $USE_FILTER_NBIT != "yes"; then
 SKIP $option
else
 TOOLTEST tnbit.ddl $option
fi
# scaleoffset
option="-H -p -d scaleoffset  tfilters.h5"
if test $USE_FILTER_SCALEOFFSET != "yes"; then
 SKIP $option
else
 TOOLTEST tscaleoffset.ddl $option
fi
# all
option="-H -p -d all  tfilters.h5"
if test $USE_FILTER_FLETCHER32 != "yes" -o  $USE_FILTER_SZIP != "yes" -o  $USE_FILTER_DEFLATE != "yes" -o  $USE_FILTER_SHUFFLE != "yes" -o $USE_FILTER_NBIT != "yes" -o  $USE_FILTER_SCALEOFFSET != "yes"; then
 SKIP $option
else
 TOOLTEST tallfilters.ddl $option
fi
# user defined
TOOLTEST tuserfilter.ddl -H  -p -d myfilter  tfilters.h5

# test for displaying objects with very long names
TOOLTEST tlonglinks.ddl tlonglinks.h5

# dimensions over 4GB, print boundary 
TOOLTEST tbigdims.ddl -d dset4gb -s 4294967284 -c 22 tbigdims.h5

# hyperslab read
TOOLTEST thyperslab.ddl thyperslab.h5


#
    
# test for displaying dataset and attribute of null space
TOOLTEST tnullspace.ddl tnullspace.h5

# test for long double (some systems do not have long double)
#TOOLTEST tldouble.ddl tldouble.h5

# test for vms
TOOLTEST tvms.ddl tvms.h5

# test for binary output
TOOLTEST1   tbin1.ddl -d integer -o $TESTDIR/out1.bin -b LE    tbinary.h5

# NATIVE default. the NATIVE test can be validated with h5import/h5diff
TOOLTEST1   tbin1.ddl -d integer -o $TESTDIR/out1.bin  -b      tbinary.h5
IMPORTTEST $TESTDIR/out1.bin -c out3.h5import -o $TESTDIR/out1.h5
DIFFTEST   tbinary.h5 $TESTDIR/out1.h5 /integer /integer

TOOLTEST1   tbin2.ddl -b BE -d float  -o $TESTDIR/out2.bin      tbinary.h5

# the NATIVE test can be validated with h5import/h5diff
TOOLTEST1   tbin3.ddl -d integer -o $TESTDIR/out3.bin -b NATIVE tbinary.h5
IMPORTTEST $TESTDIR/out3.bin -c out3.h5import -o $TESTDIR/out3.h5
DIFFTEST   tbinary.h5 $TESTDIR/out3.h5 /integer /integer

TOOLTEST1   tbin4.ddl -d double  -b FILE -o $TESTDIR/out4.bin    tbinary.h5
   
# Clean up binary output files
if test -z "$HDF5_NOCLEANUP"; then
 rm -f $TESTDIR/out[1-4].bin
 rm -f $TESTDIR/out1.h5
 rm -f $TESTDIR/out3.h5
fi

# test for dataset region references 
TOOLTEST tdatareg.ddl tdatareg.h5
TOOLTEST tdataregR.ddl -R tdatareg.h5
TOOLTEST tattrreg.ddl tattrreg.h5
TOOLTEST tattrregR.ddl -R tattrreg.h5

TOOLTEST2   tbinregR.exp -d /Dataset1 -s 0 -R -y -o $TESTDIR/tbinregR.txt    tdatareg.h5

# Clean up text output files
if test -z "$HDF5_NOCLEANUP"; then
 rm -f $TESTDIR/tbinregR.txt
fi

# tests for group creation order
# "1" tracked, "2" name, root tracked
TOOLTEST tordergr1.ddl --group=1 --sort_by=creation_order --sort_order=ascending tordergr.h5
TOOLTEST tordergr2.ddl --group=1 --sort_by=creation_order --sort_order=descending tordergr.h5
TOOLTEST tordergr3.ddl -g 2 -q name -z ascending tordergr.h5
TOOLTEST tordergr4.ddl -g 2 -q name -z descending tordergr.h5
TOOLTEST tordergr5.ddl -q creation_order tordergr.h5

# tests for attribute order
TOOLTEST torderattr1.ddl -H --sort_by=name --sort_order=ascending torderattr.h5
TOOLTEST torderattr2.ddl -H --sort_by=name --sort_order=descending torderattr.h5
TOOLTEST torderattr3.ddl -H --sort_by=creation_order --sort_order=ascending torderattr.h5
TOOLTEST torderattr4.ddl -H --sort_by=creation_order --sort_order=descending torderattr.h5

# tests for floating point user defined printf format
TOOLTEST tfpformat.ddl -m %.7f tfpformat.h5

# tests for traversal of external links
TOOLTEST textlinksrc.ddl textlinksrc.h5
TOOLTEST textlinkfar.ddl textlinkfar.h5

# test for dangling external links
TOOLTEST textlink.ddl textlink.h5

# test for error stack display (BZ2048)
TOOLTEST3 filter_fail.ddl --enable-error-stack filter_fail.h5

# test for -o -y for dataset with attributes
TOOLTEST1 tall-6.ddl -y -o $TESTDIR/data -d /g1/g1.1/dset1.1.1 tall.h5

# test for dataset packed bits 
# Set up xCMD to test or skip.
if test "$Have_Packed_Bits" = "yes"; then
    xCMD=TOOLTEST
else
    xCMD=SKIP
fi
# Limits:
# Maximum number of packed bits is 8 (for now).
# Maximum integer size is 64 (for now).
# Maximun Offset is 63 (Maximum size - 1).
# Maximum Offset+Length is 64 (Maximum size).
# Tests:
# Normal operation on both signed and unsigned int datasets.
# Sanity check
# Their rawdata output should be the same.
$xCMD tpbitsSignedWhole.ddl -d /DS08BITS -M 0,8 packedbits.h5
$xCMD tpbitsUnsignedWhole.ddl -d /DU08BITS -M 0,8 packedbits.h5
$xCMD tpbitsSignedIntWhole.ddl -d /DS16BITS -M 0,16 packedbits.h5
$xCMD tpbitsUnsignedIntWhole.ddl -d /DU16BITS -M 0,16 packedbits.h5
$xCMD tpbitsSignedLongWhole.ddl -d /DS32BITS -M 0,32 packedbits.h5
$xCMD tpbitsUnsignedLongWhole.ddl -d /DU32BITS -M 0,32 packedbits.h5
$xCMD tpbitsSignedLongLongWhole.ddl -d /DS64BITS -M 0,64 packedbits.h5
$xCMD tpbitsUnsignedLongLongWhole.ddl -d /DU64BITS -M 0,64 packedbits.h5
$xCMD tpbitsSignedLongLongWhole63.ddl -d /DS64BITS -M 0,63 packedbits.h5
$xCMD tpbitsUnsignedLongLongWhole63.ddl -d /DU64BITS -M 0,63 packedbits.h5
$xCMD tpbitsSignedLongLongWhole1.ddl -d /DS64BITS -M 1,63 packedbits.h5
$xCMD tpbitsUnsignedLongLongWhole1.ddl -d /DU64BITS -M 1,63 packedbits.h5
# Half sections
$xCMD tpbitsSigned4.ddl -d /DS08BITS -M 0,4,4,4 packedbits.h5
$xCMD tpbitsUnsigned4.ddl -d /DU08BITS -M 0,4,4,4 packedbits.h5
$xCMD tpbitsSignedInt8.ddl -d /DS16BITS -M 0,8,8,8 packedbits.h5
$xCMD tpbitsUnsignedInt8.ddl -d /DU16BITS -M 0,8,8,8 packedbits.h5
$xCMD tpbitsSignedLong16.ddl -d /DS32BITS -M 0,16,16,16 packedbits.h5
$xCMD tpbitsUnsignedLong16.ddl -d /DU32BITS -M 0,16,16,16 packedbits.h5
$xCMD tpbitsSignedLongLong32.ddl -d /DS64BITS -M 0,32,32,32 packedbits.h5
$xCMD tpbitsUnsignedLongLong32.ddl -d /DU64BITS -M 0,32,32,32 packedbits.h5
# Quarter sections
$xCMD tpbitsSigned2.ddl -d /DS08BITS -M 0,2,2,2,4,2,6,2 packedbits.h5
$xCMD tpbitsUnsigned2.ddl -d /DU08BITS -M 0,2,2,2,4,2,6,2 packedbits.h5
$xCMD tpbitsSignedInt4.ddl -d /DS16BITS -M 0,4,4,4,8,4,12,4 packedbits.h5
$xCMD tpbitsUnsignedInt4.ddl -d /DU16BITS -M 0,4,4,4,8,4,12,4 packedbits.h5
$xCMD tpbitsSignedLong8.ddl -d /DS32BITS -M 0,8,8,8,16,8,24,8 packedbits.h5
$xCMD tpbitsUnsignedLong8.ddl -d /DU32BITS -M 0,8,8,8,16,8,24,8 packedbits.h5
$xCMD tpbitsSignedLongLong16.ddl -d /DS64BITS -M 0,16,16,16,32,16,48,16 packedbits.h5
$xCMD tpbitsUnsignedLongLong16.ddl -d /DU64BITS -M 0,16,16,16,32,16,48,16 packedbits.h5
# Begin and End
$xCMD tpbitsSigned.ddl -d /DS08BITS -M 0,2,2,6 packedbits.h5
$xCMD tpbitsUnsigned.ddl -d /DU08BITS -M 0,2,2,6 packedbits.h5
$xCMD tpbitsSignedInt.ddl -d /DS16BITS -M 0,2,10,6 packedbits.h5
$xCMD tpbitsUnsignedInt.ddl -d /DU16BITS -M 0,2,10,6 packedbits.h5
$xCMD tpbitsSignedLong.ddl -d /DS32BITS -M 0,2,26,6 packedbits.h5
$xCMD tpbitsUnsignedLong.ddl -d /DU32BITS -M 0,2,26,6 packedbits.h5
$xCMD tpbitsSignedLongLong.ddl -d /DS64BITS -M 0,2,58,6 packedbits.h5
$xCMD tpbitsUnsignedLongLong.ddl -d /DU64BITS -M 0,2,58,6 packedbits.h5
# Overlapped packed bits.
$xCMD tpbitsOverlapped.ddl -d /DS08BITS -M 0,1,1,1,2,1,0,3 packedbits.h5
# Maximum number of packed bits.
$xCMD tpbitsMax.ddl -d /DS08BITS -M 0,1,1,1,2,1,3,1,4,1,5,1,6,1,7,1 packedbits.h5
# Compound type.
$xCMD tpbitsCompound.ddl -d /dset1 -M 0,1,1,1 tcompound.h5
# Array type.
$xCMD tpbitsArray.ddl -d /Dataset1 -M 0,1,1,1 tarray1.h5
# Test Error handling.
# Too many packed bits requested. Max is 8 for now.
$xCMD tpbitsMaxExceeded.ddl -d /DS08BITS -M 0,1,0,1,1,1,2,1,3,1,4,1,5,1,6,1,7,1 packedbits.h5
# Offset too large. Max is 7 (8-1) for now.
$xCMD tpbitsOffsetExceeded.ddl -d /DS08BITS -M 64,1 packedbits.h5
$xCMD tpbitsCharOffsetExceeded.ddl -d /DS08BITS -M 8,1 packedbits.h5
$xCMD tpbitsIntOffsetExceeded.ddl -d /DS16BITS -M 16,1 packedbits.h5
$xCMD tpbitsLongOffsetExceeded.ddl -d /DS32BITS -M 32,1 packedbits.h5
# Bad offset, must not be negative.
$xCMD tpbitsOffsetNegative.ddl -d /DS08BITS -M -1,1 packedbits.h5
# Bad length, must not be positive.
$xCMD tpbitsLengthPositive.ddl -d /DS08BITS -M 4,0 packedbits.h5
# Offset+Length is too large. Max is 8 for now.
$xCMD tpbitsLengthExceeded.ddl -d /DS08BITS -M 37,28 packedbits.h5
$xCMD tpbitsCharLengthExceeded.ddl -d /DS08BITS -M 2,7 packedbits.h5
$xCMD tpbitsIntLengthExceeded.ddl -d /DS16BITS -M 10,7 packedbits.h5
$xCMD tpbitsLongLengthExceeded.ddl -d /DS32BITS -M 26,7 packedbits.h5
# Incomplete pair of packed bits request.
$xCMD tpbitsIncomplete.ddl -d /DS08BITS -M 0,2,2,1,0,2,2, packedbits.h5


# Report test results and exit
if test $nerrors -eq 0 ; then
    echo "All $TESTNAME tests passed."
    exit $EXIT_SUCCESS
else
    echo "$TESTNAME tests failed with $nerrors errors."
    exit $EXIT_FAILURE
fi
