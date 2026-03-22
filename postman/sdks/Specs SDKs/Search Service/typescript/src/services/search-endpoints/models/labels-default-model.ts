import { z } from 'zod';

/**
 * Zod schema for the LabelsDefaultModel model.
 * Defines the structure and validation rules for this data type.
 * This is the shape used in application code - what developers interact with.
 */
export const labelsDefaultModel = z.lazy(() => {
  return z.object({
    score: z.number(),
    labelId: z.number(),
    labelName: z.string(),
    updateDate: z.string(),
    createDate: z.string(),
    isIncludedInRightsflow: z.number(),
    enabled: z.number(),
    isAvailableForHype: z.number(),
    isAvailableForStreaming: z.number(),
    plays: z.number().optional().nullable(),
    downloads: z.number().optional().nullable(),
    labelImageUri: z.string().optional().nullable(),
    labelImageDynamicUri: z.string().optional().nullable(),
  });
});

/**
 *
 * @typedef  {LabelsDefaultModel} labelsDefaultModel
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {string}
 * @property {string}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {number}
 * @property {string}
 * @property {string}
 */
export type LabelsDefaultModel = z.infer<typeof labelsDefaultModel>;

/**
 * Zod schema for mapping API responses to the LabelsDefaultModel application shape.
 * Handles any property name transformations from the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const labelsDefaultModelResponse = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      label_id: z.number(),
      label_name: z.string(),
      update_date: z.string(),
      create_date: z.string(),
      is_included_in_rightsflow: z.number(),
      enabled: z.number(),
      is_available_for_hype: z.number(),
      is_available_for_streaming: z.number(),
      plays: z.number().optional().nullable(),
      downloads: z.number().optional().nullable(),
      label_image_uri: z.string().optional().nullable(),
      label_image_dynamic_uri: z.string().optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      labelId: data['label_id'],
      labelName: data['label_name'],
      updateDate: data['update_date'],
      createDate: data['create_date'],
      isIncludedInRightsflow: data['is_included_in_rightsflow'],
      enabled: data['enabled'],
      isAvailableForHype: data['is_available_for_hype'],
      isAvailableForStreaming: data['is_available_for_streaming'],
      plays: data['plays'],
      downloads: data['downloads'],
      labelImageUri: data['label_image_uri'],
      labelImageDynamicUri: data['label_image_dynamic_uri'],
    }));
});

/**
 * Zod schema for mapping the LabelsDefaultModel application shape to API requests.
 * Handles any property name transformations required by the API schema.
 * If property names match the API schema exactly, this is identical to the application shape.
 */
export const labelsDefaultModelRequest = z.lazy(() => {
  return z
    .object({
      score: z.number(),
      labelId: z.number(),
      labelName: z.string(),
      updateDate: z.string(),
      createDate: z.string(),
      isIncludedInRightsflow: z.number(),
      enabled: z.number(),
      isAvailableForHype: z.number(),
      isAvailableForStreaming: z.number(),
      plays: z.number().optional().nullable(),
      downloads: z.number().optional().nullable(),
      labelImageUri: z.string().optional().nullable(),
      labelImageDynamicUri: z.string().optional().nullable(),
    })
    .transform((data) => ({
      score: data['score'],
      label_id: data['labelId'],
      label_name: data['labelName'],
      update_date: data['updateDate'],
      create_date: data['createDate'],
      is_included_in_rightsflow: data['isIncludedInRightsflow'],
      enabled: data['enabled'],
      is_available_for_hype: data['isAvailableForHype'],
      is_available_for_streaming: data['isAvailableForStreaming'],
      plays: data['plays'],
      downloads: data['downloads'],
      label_image_uri: data['labelImageUri'],
      label_image_dynamic_uri: data['labelImageDynamicUri'],
    }));
});
