/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <dirent.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>

#ifdef __linux__
#include <sys/vfs.h>
#endif
#ifdef __APPLE__
#include <sys/uio.h>
#include <sys/mount.h>
#endif
#include <errno.h>
#include <assert.h>
#include "ByteSwapUtils.h"
#include "datahdr.h"
#include "LinuxCompat.h"
// #include "Raw2Wells.h"
#include "Image.h"
#include "crop/Acq.h"
#include "IonVersion.h"
#include "Utils.h"
#include "PinnedWellReporter.h"

void usage(int cropx, int cropy, int cropw, int croph) {
  fprintf (stdout, "Crop - Utility to extract a subregion from a raw data set.  Output directory is created named './converted'.\n");
  fprintf (stdout, "options:\n");
  fprintf (stdout, "   -a\tOutput flat files; ascii text\n");
  fprintf (stdout, "   -b\tUse alternate sampling rate\n");
  fprintf (stdout, "   -x\tStarting x axis position (origin lower left) Default: %d\n",cropx);
  fprintf (stdout, "   -y\tStarting y axis position (origin lower left) Default: %d\n",cropy);
  fprintf (stdout, "   -w\tWidth of crop region Default: %d\n",cropw);
  fprintf (stdout, "   -h\tHeight of crop region Default: %d\n",croph);
  fprintf (stdout, "   -s\tSource directory containing raw data\n");
  fprintf (stdout, "   -f\tConverts only the one file named as an argument\n");
  fprintf (stdout, "   -z\tTells the image loader not to wait for a non-existent file\n");
  fprintf (stdout, "   -H\tPrints this message and exits.\n");
  fprintf (stdout, "   -v\tPrints version information and exits.\n");
  fprintf (stdout, "   -c\tOutput a variable rate frame compressed data set.  Default to whole chip\n");
  fprintf (stdout, "   -n\tOutput a non-variable rate frame compressed data set.\n");
  fprintf (stdout, "   -d\tOutput directory.\n");
  fprintf (stdout, "\n");
  fprintf (stdout, "usage:\n");
  fprintf (stdout, "   Crop -s /results/analysis/PGM/testRun1\n");
  fprintf (stdout, "\n");
  exit (1);
}

int main(int argc, char *argv[])
{
	int cropx = 624, cropy = 125, cropw = 100, croph = 100;
	char *expPath  = const_cast<char*>(".");
	char *destPath = const_cast<char*>("./converted");
	char *oneFile = NULL;
	int alternate_sampling=0;
	int doAscii = 0;
	int vfc = 1;
	int dont_retry = 0;
	if (argc == 1) {
	  usage(cropx, cropy, cropw, croph);
	}
	int argcc = 1;
	while (argcc < argc) {
		switch (argv[argcc][1]) {
			case 'a':
				doAscii = 1;
			break;
			
			case 'x':
				argcc++;
				cropx = atoi(argv[argcc]);
			break;

			case 'y':
				argcc++;
				cropy = atoi(argv[argcc]);
			break;

			case 'w':
				argcc++;
				cropw = atoi(argv[argcc]);
			break;

			case 'h':
				argcc++;
				// don't segfault if called with -h (user expects help)
				if (argcc >= argc) {
				  usage(cropx, cropy, cropw, croph);
				}
				croph = atoi(argv[argcc]);
			break;
		
			case 's':
				argcc++;
				expPath = argv[argcc];
			break;

			case 'f':
				argcc++;
				oneFile = argv[argcc];
			break;

			case 'z':
				dont_retry = 1;
			break;

			case 'c':
				vfc=1;
				cropx=0;
				cropy=0;
				cropw=0;
				croph=0;
			break;

			case 'n':
				vfc=0;
			break;

			case 'b':
				alternate_sampling=1;
			break;

			case 'v':
				fprintf (stdout, "%s", IonVersion::GetFullVersion("Crop").c_str());
				exit (0);
			break;
			case 'H':
			  usage(cropx, cropy, cropw, croph);
			  break;
			case 'd':
				argcc++;
				destPath = argv[argcc];
			break;

			default:
				argcc++;
				fprintf (stdout, "\n");
				
		}
		argcc++;
	}

	char name[MAX_PATH_LENGTH];
	char destName[MAX_PATH_LENGTH];
	int i;
	Image loader;
	Acq saver;
	int mode = 0;
	i = 0;
	bool allocate = true;
	char **nameList;
	char *defaultNameList[] = {"beadfind_post_0000.dat", "beadfind_post_0001.dat", "beadfind_post_0002.dat", "beadfind_post_0003.dat",
				"beadfind_pre_0000.dat", "beadfind_pre_0001.dat", "beadfind_pre_0002.dat", "beadfind_pre_0003.dat",
				"prerun_0000.dat", "prerun_0001.dat", "prerun_0002.dat", "prerun_0003.dat", "prerun_0004.dat"};
	int nameListLen;

	// Turn off this feature which sucks the life out of performance.
	PWR::PinnedWellReporter::Instance( false );
	
	// if requested...do not bother waiting for the files to show up
	if (dont_retry)
		loader.SetTimeout(1,1);

	if (oneFile != NULL)
	{
		nameList = &oneFile;
		nameListLen = 1;
		mode = 1;
	}
	else
	{
		nameList = defaultNameList;
		nameListLen = sizeof(defaultNameList)/sizeof(defaultNameList[0]);
	}

    // Create results folder
	umask (0);	// make permissive permissions so its easy to delete.
    if (mkdir (destPath, 0777))
    {
        if (errno == EEXIST) {
            //already exists? well okay...
        }
        else {
            perror (destPath);
            exit (1);
        }
    }
	
	// Copy explog.txt file: all .txt files
	char cmd[1024];
	sprintf (cmd, "cp -v %s/*.txt %s", expPath, destPath);
	assert(system(cmd) == 0);
	
	while (mode < 2) {
		if (mode == 0) {
			sprintf(name, "%s/acq_%04d.dat", expPath, i);
			sprintf(destName, "%s/acq_%04d.dat", destPath, i);
		} else if (mode == 1) {
			if(i >= nameListLen)
				break;
			sprintf(name, "%s/%s", expPath, nameList[i]);
			sprintf(destName, "%s/%s", destPath, nameList[i]);
		} else
			break;
		if (loader.LoadRaw(name, 0, allocate, false)) {
			allocate = false;
			const RawImage *raw = loader.GetImage();
			struct timeval tv;
			double startT;
			double stopT;
			gettimeofday(&tv, NULL);
			startT = (double) tv.tv_sec + ((double) tv.tv_usec/1000000);

			printf("Converting raw data %d %d frames: %d UncompFrames: %d\n", raw->cols, raw->rows, raw->frames, raw->uncompFrames);
			saver.SetData(&loader);
			if (doAscii) {
				if (!saver.WriteAscii(destName, cropx, cropy, cropw, croph))
					break;
			}
			else {
				if(vfc)
				{
					if (!saver.WriteVFC(destName, cropx, cropy, cropw, croph))
						break;
				}
				else
				{
					if (!saver.Write(destName, cropx, cropy, cropw, croph))
						break;
				}
			}
			gettimeofday(&tv, NULL);
			stopT = (double) tv.tv_sec + ((double) tv.tv_usec/1000000);
			printf("Converted: %s in %0.2lf sec\n", name,stopT - startT);
			fflush (stdout);
			i++;
		} else {
			if ((mode == 1 && i >= 12) || (mode == 0)) {
				mode++;
				i = 0;
				allocate = true;
			} else
				i++;
		}
	}
}

