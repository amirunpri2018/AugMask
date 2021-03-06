import numpy as np
import cv2

from core.config import cfg
import utils.blob as blob_utils
import roi_data.rpn


def get_minibatch_blob_names(is_training=True):
    """Return blob names in the order in which they are read by the data loader.
    """
    # data blob: holds a batch of N images, each with 3 channels
    blob_names = ['data']
    if cfg.RPN.RPN_ON:
        # RPN-only or end-to-end Faster R-CNN
        blob_names += roi_data.rpn.get_rpn_blob_names(is_training=is_training)
    elif cfg.RETINANET.RETINANET_ON:
        raise NotImplementedError
    else:
        # Fast R-CNN like models trained on precomputed proposals
        blob_names += roi_data.fast_rcnn.get_fast_rcnn_blob_names(
            is_training=is_training
        )
    return blob_names


def get_minibatch(roidb, coco):
    """Given a roidb, construct a minibatch sampled from it."""
    # We collect blobs from each image onto a list and then concat them into a
    # single tensor, hence we initialize each blob to an empty list
    blobs = {k: [] for k in get_minibatch_blob_names()}

    # Get the input image blob
    im_blob, im_scales, roidb = _get_image_blob(roidb, coco)
    blobs['data'] = im_blob
    if cfg.RPN.RPN_ON:
        # RPN-only or end-to-end Faster/Mask R-CNN
        valid = roi_data.rpn.add_rpn_blobs(blobs, im_scales, roidb)
    elif cfg.RETINANET.RETINANET_ON:
        raise NotImplementedError
    else:
        # Fast R-CNN like models trained on precomputed proposals
        valid = roi_data.fast_rcnn.add_fast_rcnn_blobs(blobs, im_scales, roidb)
    return blobs, valid


def _get_image_blob(roidb, coco):
    """Builds an input blob from the images in the roidb at the specified
    scales.
    """
    num_images = len(roidb)
    # Sample random scales to use for each image in this batch
    scale_inds = np.random.randint(
        0, high=len(cfg.TRAIN.SCALES), size=num_images)
    processed_ims = []
    im_scales = []
    for i in range(num_images):
        im = cv2.imread(roidb[i]['image'])
        assert im is not None, \
            'Failed to read image \'{}\''.format(roidb[i]['image'])
                    
        # AUG BEGIN--------------------------------
        backupim = im
        backuproidb = roidb[i]
        try:    
            from AugSeg.get_instance_group import extract
            from AugSeg.affine_transform import transform_image, transform_annotation
            img_id = roidb[i]['id']
            ann_ids = coco.getAnnIds(imgIds=img_id)
            anns = coco.loadAnns(ann_ids)
            background, instances_list, transforms_list, groupbnds_list, groupidx_list = extract(anns, im)
            new_img = transform_image(background, instances_list, transforms_list)
            new_ann = transform_annotation(anns, transforms_list, groupbnds_list, groupidx_list,
                                           background.shape[1], background.shape[0])
            im = new_img
            from datasetsAug.roidb import combined_roidb_for_training
            new_roidb, ratio_list, ratio_index = combined_roidb_for_training( \
                ('coco_2017_train',), cfg.TRAIN.PROPOSAL_FILES, \
                img_id, new_ann, coco
                )
            if roidb[i]['flipped']:
                roidb[i] = new_roidb[1]
            else:
                roidb[i] = new_roidb[0]
        except:
            roidb[i] = backuproidb
            im = backupim
        # AUG END----------------------------------
        
        # If NOT using opencv to read in images, uncomment following lines
        # if len(im.shape) == 2:
        #     im = im[:, :, np.newaxis]
        #     im = np.concatenate((im, im, im), axis=2)
        # # flip the channel, since the original one using cv2
        # # rgb -> bgr
        # im = im[:, :, ::-1]
        if roidb[i]['flipped']:
            im = im[:, ::-1, :]

        target_size = cfg.TRAIN.SCALES[scale_inds[i]]
        im, im_scale = blob_utils.prep_im_for_blob(
            im, cfg.PIXEL_MEANS, [target_size], cfg.TRAIN.MAX_SIZE)
        im_scales.append(im_scale[0])
        processed_ims.append(im[0])

    # Create a blob to hold the input images [n, c, h, w]
    blob = blob_utils.im_list_to_blob(processed_ims)

    return blob, im_scales, roidb
