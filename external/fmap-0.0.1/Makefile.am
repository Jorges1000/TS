bin_PROGRAMS = fmap

GLOBAL_SOURCES = \
				 src/util/fmap_alloc.h src/util/fmap_alloc.c \
				 src/util/fmap_definitions.h src/util/fmap_definitions.c \
				 src/util/fmap_error.h src/util/fmap_error.c \
				 src/util/fmap_fibheap.h src/util/fmap_fibheap.c \
				 src/util/fmap_hash.h \
				 src/util/fmap_progress.h src/util/fmap_progress.c \
				 src/util/fmap_sam.h src/util/fmap_sam.c \
				 src/util/fmap_string.h src/util/fmap_string.c \
				 src/util/fmap_sort.h \
				 src/util/fmap_vec.h \
				 src/seq/fmap_fq.h src/seq/fmap_fq.c \
				 src/seq/fmap_sff.h src/seq/fmap_sff.c \
				 src/seq/fmap_seq.h src/seq/fmap_seq.c \
				 src/io/fmap_file.h src/io/fmap_file.c \
				 src/io/fmap_fq_io.h src/io/fmap_fq_io.c \
				 src/io/fmap_sff_io.h src/io/fmap_sff_io.c \
				 src/io/fmap_seq_io.h src/io/fmap_seq_io.c \
				 src/index/fmap_bwt.h src/index/fmap_bwt.c \
				 src/index/fmap_bwtl.h src/index/fmap_bwtl.c \
				 src/index/fmap_bwt_gen.h src/index/fmap_bwt_gen.c \
				 src/index/fmap_bwt_match.h src/index/fmap_bwt_match.c \
				 src/index/fmap_index.h src/index/fmap_index.c \
				 src/index/fmap_refseq.h src/index/fmap_refseq.c \
				 src/index/fmap_sa.c src/index/fmap_sa.h \
				 src/sw/fmap_sw.h src/sw/fmap_sw.c \
				 src/sw/fmap_fsw.h src/sw/fmap_fsw.c 

fmap_SOURCES = \
			   ${GLOBAL_SOURCES} \
			   src/server/fmap_server.h src/server/fmap_server.c \
			   src/server/fmap_shm.h src/server/fmap_shm.c \
			   src/misc/fmap_sam2fs_aux.h src/misc/fmap_sam2fs_aux.c \
			   src/misc/fmap_sam2fs.h src/misc/fmap_sam2fs.c \
			   src/debug/fmap_debug_exact.h src/debug/fmap_debug_exact.c \
			   src/map/fmap_map_util.h src/map/fmap_map_util.c \
			   src/map/fmap_map1.h src/map/fmap_map1.c \
			   src/map/fmap_map1_aux.h src/map/fmap_map1_aux.c \
			   src/map/fmap_map2.h src/map/fmap_map2.c \
			   src/map/fmap_map2_aux.h src/map/fmap_map2_aux.c \
			   src/map/fmap_map2_chain.h src/map/fmap_map2_chain.c \
			   src/map/fmap_map2_core.h src/map/fmap_map2_core.c \
			   src/map/fmap_map2_mempool.h src/map/fmap_map2_mempool.c \
			   src/map/fmap_map3.h src/map/fmap_map3.c \
			   src/map/fmap_map3_aux.h src/map/fmap_map3_aux.c \
			   src/map/fmap_map_all.h src/map/fmap_map_all.c \
			   src/fmap_main.h src/fmap_main.c

fmap_LDADD = 

#noinst_LIBRARIES = libfmap.a
#libfmap_a_SOURCES = ${GLOBAL_SOURCES} 

EXTRA_DIST = LICENSE \
			 autogen.sh 

SUBDIRS = .

docdir = ${datadir}/doc/${PACKAGE}
dist_doc_DATA = LICENSE doc/fmap-book.pdf
