package com.searchservicesdk.validation.validators;

import com.searchservicesdk.validation.Violation;
import java.util.ArrayList;
import java.util.List;

/**
 * Validator for numeric values with minimum and maximum constraints.
 * Supports inclusive and exclusive bounds for range validation.
 *
 * @param <T> The numeric type to validate (Integer, Long, Double, etc.)
 */
public class NumericValidator<T extends Number> extends AbstractValidator<T> {

  private T minValue;
  private boolean minInclusive;
  private T maxValue;
  private boolean maxInclusive;

  public NumericValidator(String fieldName) {
    super(fieldName);
  }

  public NumericValidator() {}

  /**
   * Sets the minimum value constraint (inclusive by default).
   *
   * @param min The minimum allowed value
   * @return This validator for method chaining
   */
  public NumericValidator<T> min(T min) {
    return min(min, true);
  }

  /**
   * Sets the minimum value constraint with inclusive/exclusive option.
   *
   * @param min The minimum allowed value
   * @param inclusive Whether the minimum is inclusive (>=) or exclusive (>)
   * @return This validator for method chaining
   */
  public NumericValidator<T> min(T min, boolean inclusive) {
    this.minValue = min;
    this.minInclusive = inclusive;
    return this;
  }

  /**
   * Sets the maximum value constraint (inclusive by default).
   *
   * @param max The maximum allowed value
   * @return This validator for method chaining
   */
  public NumericValidator<T> max(T max) {
    return max(max, true);
  }

  /**
   * Sets the maximum value constraint with inclusive/exclusive option.
   *
   * @param max The maximum allowed value
   * @param inclusive Whether the maximum is inclusive (<=) or exclusive (<)
   * @return This validator for method chaining
   */
  public NumericValidator<T> max(T max, boolean inclusive) {
    this.maxValue = max;
    this.maxInclusive = inclusive;
    return this;
  }

  /**
   * Validates a numeric value against configured constraints.
   *
   * @param value The number to validate
   * @return Array of violations if validation fails, empty array if valid
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

    List<Violation> violations = new ArrayList<>();

    if (this.minValue != null) {
      if (this.minInclusive) {
        if (value.doubleValue() < this.minValue.doubleValue()) {
          violations.add(
            new Violation(
              getFieldName(),
              String.format("must be greater than or equal to %s", this.minValue)
            )
          );
        }
      } else {
        if (value.doubleValue() <= this.minValue.doubleValue()) {
          violations.add(
            new Violation(getFieldName(), String.format("must be greater than %s", this.minValue))
          );
        }
      }
    }

    if (this.maxValue != null) {
      if (this.maxInclusive) {
        if (value.doubleValue() > this.maxValue.doubleValue()) {
          violations.add(
            new Violation(
              getFieldName(),
              String.format("must be less than or equal to %s", this.maxValue)
            )
          );
        }
      } else {
        if (value.doubleValue() >= this.maxValue.doubleValue()) {
          violations.add(
            new Violation(getFieldName(), String.format("must be less than %s", this.maxValue))
          );
        }
      }
    }

    return violations.toArray(new Violation[0]);
  }
}
