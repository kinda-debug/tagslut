package com.searchservicesdk.validation.validators.modelValidators;

import com.searchservicesdk.models.ReleasesSearchSearchV1ReleasesGetParameters;
import com.searchservicesdk.validation.Violation;
import com.searchservicesdk.validation.ViolationAggregator;
import com.searchservicesdk.validation.validators.NumericValidator;

/**
 * Validator implementation for ReleasesSearchSearchV1ReleasesGetParameters model.
 * Validates all fields and nested structures according to the model's constraints.
 */
public class ReleasesSearchSearchV1ReleasesGetParametersValidator
  extends AbstractModelValidator<ReleasesSearchSearchV1ReleasesGetParameters> {

  /**
   * Creates a validator with a field name for nested validation paths.
   *
   * @param fieldName The field name to use in violation paths
   */
  public ReleasesSearchSearchV1ReleasesGetParametersValidator(String fieldName) {
    super(fieldName);
  }

  /**
   * Creates a validator for root-level validation.
   */
  public ReleasesSearchSearchV1ReleasesGetParametersValidator() {}

  /**
   * Validates the ReleasesSearchSearchV1ReleasesGetParameters model's fields and constraints.
   *
   * @param requestParameters The model instance to validate
   * @return Array of violations found during validation
   */
  @Override
  protected Violation[] validateModel(
    ReleasesSearchSearchV1ReleasesGetParameters requestParameters
  ) {
    return new ViolationAggregator()
      .add(
        new NumericValidator<Long>("releaseNameWeight")
          .min(0L)
          .max(10L)
          .optional()
          .validate(requestParameters.getReleaseNameWeight())
      )
      .add(
        new NumericValidator<Long>("labelNameWeight")
          .min(0L)
          .max(10L)
          .optional()
          .validate(requestParameters.getLabelNameWeight())
      )
      .aggregate();
  }
}
