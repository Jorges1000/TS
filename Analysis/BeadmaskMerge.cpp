/* Copyright (C) 2010 Ion Torrent Systems, Inc. All Rights Reserved */
//

#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <libgen.h>
#include <string.h>
#include <string>
#include <sstream>
#include <vector>
#include <iostream>
#include "IonVersion.h"
#include "Mask.h"
#include "LinuxCompat.h"
#include "Utils.h"

int main (int argc, char *argv[])
{
 	// process command-line args
    char* beadfindFileName = NULL;
	char* outputFileName = NULL;
    std::vector<std::string> folders;
    int c;
    while ( (c = getopt (argc, argv, "i:o:ehm:v")) != -1 )
        {
            switch (c)
                {
                case 'i': beadfindFileName = strdup(optarg); break;
                case 'o': outputFileName = strdup(optarg); break;
                case 'h':
                    fprintf (stdout, "%s -i in -o out folders \n", argv[0]);
                    exit (0);
                    break;
                case 'v':   //version
                    fprintf (stdout, "%s", IonVersion::GetFullVersion("BeadmaskMerge").c_str());
                    return (0);
                    break;
                default:
                    fprintf (stdout, "whatever");
                    break;
                }
        }
    
    for (c = optind; c < argc; c++) {
        folders.push_back(argv[c]);
    }
   
	if (!beadfindFileName) {
		fprintf (stderr, "No input file specified\n");
		exit (1);
	}
	else {
		fprintf (stdout, "Reading from file: %s\n", beadfindFileName);
	}

	if (folders.size() < 1) {
		fprintf (stderr, "No input directories specified\n");
		exit (1);
	}
	else {
        for (unsigned int f=0;f<folders.size();f++) {
            fprintf (stdout, "Reading from folder: %s\n", folders[f].c_str());
        }
	}

	if (!outputFileName) {
		fprintf (stderr, "No output file specified\n");
		exit (1);
	}
	else {
		fprintf (stdout, "Writing into file: %s\n", outputFileName);
	}
    
    
    char* size = GetProcessParam (folders[0].c_str(), "Chip" );
    int wt=atoi(strtok (size,","));
    int ht=atoi(strtok(NULL, ","));

    Mask fullmask(wt,ht);

    //  mask value
    uint16_t mask = 0;


    for (unsigned int f=0;f<folders.size();f++) {

        std::stringstream ss;
        ss << folders[f] << "/" << std::string(beadfindFileName);
        FILE *fp = NULL;
        fopen_s (&fp, ss.str().c_str(), "rb");
        if (!fp) {
            perror (ss.str().c_str());
            exit (1);
        }

        int32_t w = 0;
        int32_t h = 0;
        //  number of rows - height
        if ((fread (&h, sizeof(uint32_t), 1, fp )) != 1) {
            perror ("Reading width");
            exit (1);
        }
        //  number of columns - width
        if ((fread (&w, sizeof(uint32_t), 1, fp )) != 1) {
            perror ("Reading height");
            exit (1);
        }

        // extract offsets from folder name
        char* size = GetProcessParam (folders[f].c_str(), "Block" );
        int xoffset=atoi(strtok (size,","));
        int yoffset=atoi(strtok(NULL, ","));

        for (int y = 0; y < h; y++) {
            for (int x = 0; x < w; x++) {
                if ((fread (&mask, sizeof(uint16_t), 1, fp)) != 1) {	// Mask values , row-major
                    perror ("Reading binary mask values");
                    exit (1);
                }

                //fullmask.SetBarcodeId(x+xoffset,y+yoffset,mask); // same as next line
                fullmask[wt*(yoffset+y)+xoffset+x] = mask;
            }
        }
        fclose (fp);
    }
    fullmask.WriteRaw(outputFileName);
    
    exit (0);
}
