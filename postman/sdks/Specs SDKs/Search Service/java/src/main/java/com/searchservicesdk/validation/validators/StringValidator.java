package com.searchservicesdk.validation.validators;

import com.searchservicesdk.validation.Violation;
import java.util.ArrayList;
import java.util.List;

/**
 * Validator for string values with length and pattern constraints.
 * Provides a fluent API for configuring validation rules.
 */
public class StringValidator extends AbstractValidator<String> {

  private Integer minLength;
  private Integer maxLength;
  private String pattern;

  public StringValidator(String fieldName) {
    super(fieldName);
  }

  public StringValidator() {}

  /**
   * Sets the minimum length constraint.
   *
   * @param minLength The minimum allowed length
   * @return This validator for method chaining
   */
  public StringValidator minLength(Integer minLength) {
    this.minLength = minLength;
    return this;
  }

  /**
   * Sets the maximum length constraint.
   *
   * @param maxLength The maximum allowed length
   * @return This validator for method chaining
   */
  public StringValidator maxLength(Integer maxLength) {
    this.maxLength = maxLength;
    return this;
  }

  /**
   * Sets the regex pattern constraint.
   *
   * @param pattern The regex pattern the string must match
   * @return This validator for method chaining
   */
  public StringValidator pattern(String pattern) {
    this.pattern = pattern;
    return this;
  }

  /**
   * Validates a string value against configured constraints.
   *
   * @param value The string to validate
   * @return Array of violations if validation fails, empty array if valid
   */
  @Override
  public Violation[] validate(String value) {
    Violation requiredViolation = validateRequired(value);
    if (requiredViolation != null) {
      return new Violation[] { requiredViolation };
    }
    if (value == null) {
      return new Violation[0];
    }

    List<Violation> violations = new ArrayList<>();

    if (minLength != null && value.length() < minLength) {
      violations.add(
        new Violation(
          getFieldName(),
          String.format("must be at least %d characters long", minLength)
        )
      );
    }
    if (maxLength != null && value.length() > maxLength) {
      violations.add(
        new Violation(
          getFieldName(),
          String.format("must be at most %d characters long", maxLength)
        )
      );
    }
    if (pattern != null && !value.matches(pattern)) {
      violations.add(
        new Violation(getFieldName(), String.format("must match pattern %s", pattern))
      );
    }

    return violations.toArray(new Violation[0]);
  }
}
