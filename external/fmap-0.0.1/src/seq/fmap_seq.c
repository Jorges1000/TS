#include <stdlib.h>

#include "../util/fmap_error.h"
#include "../util/fmap_alloc.h"
#include "fmap_fq.h"
#include "fmap_sff.h"
#include "fmap_seq.h"

fmap_seq_t *
fmap_seq_init(int8_t type)
{
  fmap_seq_t *seq = NULL;

  seq = fmap_calloc(1, sizeof(fmap_seq_t), "seq");
  seq->type = type;

  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      seq->data.fq = fmap_fq_init();
      break;
    case FMAP_SEQ_TYPE_SFF:
      seq->data.sff = fmap_sff_init();
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }

  return seq;
}

void
fmap_seq_destroy(fmap_seq_t *seq)
{
  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      fmap_fq_destroy(seq->data.fq);
      break;
    case FMAP_SEQ_TYPE_SFF:
      fmap_sff_destroy(seq->data.sff);
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }
  free(seq);
}

fmap_seq_t *
fmap_seq_clone(fmap_seq_t *seq)
{
  fmap_seq_t *ret = NULL;

  ret = fmap_calloc(1, sizeof(fmap_seq_t), "ret");
  ret->type = seq->type;

  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      ret->data.fq = fmap_fq_clone(seq->data.fq);
      break;
    case FMAP_SEQ_TYPE_SFF:
      ret->data.sff = fmap_sff_clone(seq->data.sff);
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }

  return ret;
}

void
fmap_seq_reverse_compliment(fmap_seq_t *seq)
{
  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      fmap_fq_reverse_compliment(seq->data.fq);
      break;
    case FMAP_SEQ_TYPE_SFF:
      fmap_sff_reverse_compliment(seq->data.sff);
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }
}

void
fmap_seq_to_int(fmap_seq_t *seq)
{
  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      fmap_fq_to_int(seq->data.fq);
      break;
    case FMAP_SEQ_TYPE_SFF:
      fmap_sff_to_int(seq->data.sff);
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }
}

fmap_string_t *
fmap_seq_get_name(fmap_seq_t *seq)
{
  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      return seq->data.fq->name;
      break;
    case FMAP_SEQ_TYPE_SFF:
      return seq->data.sff->rheader->name;
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }
  return NULL;
}

inline fmap_string_t *
fmap_seq_get_bases(fmap_seq_t *seq)
{
  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      return fmap_fq_get_bases(seq->data.fq);
      break;
    case FMAP_SEQ_TYPE_SFF:
      return fmap_sff_get_bases(seq->data.sff);
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }
  return NULL;
}

inline fmap_string_t *
fmap_seq_get_qualities(fmap_seq_t *seq)
{
  switch(seq->type) {
    case FMAP_SEQ_TYPE_FQ:
      return fmap_fq_get_qualities(seq->data.fq);
      break;
    case FMAP_SEQ_TYPE_SFF:
      return fmap_sff_get_qualities(seq->data.sff);
      break;
    default:
      fmap_error("type is unrecognized", Exit, OutOfRange);
      break;
  }
  return NULL;
}

inline void
fmap_seq_remove_key_sequence(fmap_seq_t *seq)
{
  if(FMAP_SEQ_TYPE_SFF != seq->type) return; // ignore
  fmap_sff_remove_key_sequence(seq->data.sff);
}

fmap_seq_t *
fmap_seq_sff2fq(fmap_seq_t *seq)
{
  int32_t i;
  fmap_seq_t *ret= NULL;
  
  if(seq->type == FMAP_SEQ_TYPE_FQ) return fmap_seq_clone(seq);

  //Note:  ignore the comment field
  ret = fmap_seq_init(FMAP_SEQ_TYPE_FQ);
  fmap_string_copy(ret->data.fq->name, seq->data.sff->rheader->name); // name
  fmap_string_copy(ret->data.fq->seq, seq->data.sff->read->bases); // seq
  fmap_string_copy(ret->data.fq->qual, seq->data.sff->read->quality); // qual
  ret->data.fq->is_int = seq->data.sff->is_int; // is in integer format

  // remove key sequence
  for(i=0;i<ret->data.fq->seq->l - seq->data.sff->gheader->key_length;i++) {
      ret->data.fq->seq->s[i] = ret->data.fq->seq->s[i + seq->data.sff->gheader->key_length];
      ret->data.fq->qual->s[i] = ret->data.fq->qual->s[i + seq->data.sff->gheader->key_length];
  }
  ret->data.fq->seq->l -= seq->data.sff->gheader->key_length;
  ret->data.fq->qual->l -= seq->data.sff->gheader->key_length;

  return ret;
}
