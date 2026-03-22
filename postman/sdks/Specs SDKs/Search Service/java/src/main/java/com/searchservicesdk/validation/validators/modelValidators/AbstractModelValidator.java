package com.searchservicesdk.validation.validators.modelValidators;

import com.searchservicesdk.validation.Violation;
import com.searchservicesdk.validation.validators.AbstractValidator;
import java.util.Arrays;

/**
 * Abstract base validator for complex model objects.
 * Extends AbstractValidator to add model-specific validation with proper path handling.
 * Subclasses implement validateModel() to define validation rules for specific model types.
 */
public abstract class AbstractModelValidator<T> extends AbstractValidator<T> {

  /**
   * Creates a validator with a field name for error path construction.
   *
   * @param fieldName The field name to use in violation paths
   */
  public AbstractModelValidator(String fieldName) {
    super(fieldName);
  }

  /**
   * Creates a validator without a field name (for root-level validation).
   */
  public AbstractModelValidator() {}

  /**
   * Validates the model's internal structure and constraints.
   * Subclasses implement this to define model-specific validation rules.
   *
   * @param value The model instance to validate
   * @return Array of violations found during validation
   */
  protected abstract Violation[] validateModel(T value);

  /**
   * Validates a model value including required checks and model-specific validation.
   * Prepends the field name to all violation paths for proper error reporting.
   *
   * @param value The value to validate
   * @return Array of violations found
   */
  @Override
  public Violation[] validate(T value) {
    Violation requiredViolation = validateRequired(value);
    if (requiredViolation != null) {
      return new Violation[] { requiredViolation };
    }
    if (value == null) {
      return new Violation[0];
    }

    Violation[] violations = validateModel(value);
    if (violations.length == 0) {
      return violations;
    }

    return Arrays.stream(violations)
      .map(violation -> {
        String newPath = violation.getPath().isEmpty()
          ? getFieldName()
          : String.format("%s.%s", getFieldName(), violation.getPath());
        return new Violation(newPath, violation.getMessage());
      })
      .toArray(Violation[]::new);
  }
}
