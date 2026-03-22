package com.searchservicesdk.validation.validators.modelValidators;

import com.searchservicesdk.models.TracksSearchSearchV1TracksGetParameters;
import com.searchservicesdk.validation.Violation;
import com.searchservicesdk.validation.ViolationAggregator;
import com.searchservicesdk.validation.validators.NumericValidator;

/**
 * Validator implementation for TracksSearchSearchV1TracksGetParameters model.
 * Validates all fields and nested structures according to the model's constraints.
 */
public class TracksSearchSearchV1TracksGetParametersValidator
  extends AbstractModelValidator<TracksSearchSearchV1TracksGetParameters> {

  /**
   * Creates a validator with a field name for nested validation paths.
   *
   * @param fieldName The field name to use in violation paths
   */
  public TracksSearchSearchV1TracksGetParametersValidator(String fieldName) {
    super(fieldName);
  }

  /**
   * Creates a validator for root-level validation.
   */
  public TracksSearchSearchV1TracksGetParametersValidator() {}

  /**
   * Validates the TracksSearchSearchV1TracksGetParameters model's fields and constraints.
   *
   * @param requestParameters The model instance to validate
   * @return Array of violations found during validation
   */
  @Override
  protected Violation[] validateModel(TracksSearchSearchV1TracksGetParameters requestParameters) {
    return new ViolationAggregator()
      .add(
        new NumericValidator<Long>("mixNameWeight")
          .min(0L)
          .max(10L)
          .optional()
          .validate(requestParameters.getMixNameWeight())
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
