package com.tagslutapisdk.validation.validators;

import com.tagslutapisdk.validation.Violation;
import lombok.Getter;

/**
 * Abstract base class for all validators providing common functionality.
 * Handles field name tracking and required/optional validation.
 *
 * @param <T> The type of value to validate
 */
public abstract class AbstractValidator<T> implements Validator<T> {

  @Getter
  private String fieldName;

  @Getter
  private boolean isRequired = false;

  public AbstractValidator(String fieldName) {
    this.fieldName = fieldName;
  }

  public AbstractValidator() {
    this.fieldName = "";
  }

  /**
   * Marks this field as required (must not be null).
   *
   * @return This validator for method chaining
   */
  public AbstractValidator<T> required() {
    this.isRequired = true;
    return this;
  }

  /**
   * Marks this field as optional (may be null).
   *
   * @return This validator for method chaining
   */
  public AbstractValidator<T> optional() {
    this.isRequired = false;
    return this;
  }

  /**
   * Sets the field name for violation messages.
   *
   * @param fieldName The field name
   * @return This validator for method chaining
   */
  public AbstractValidator<T> setFieldName(String fieldName) {
    this.fieldName = fieldName;
    return this;
  }

  /**
   * Validates that a required field is not null.
   *
   * @param value The value to check
   * @return A violation if the field is required and null, otherwise null
   */
  protected Violation validateRequired(T value) {
    if (isRequired() && value == null) {
      return new Violation(getFieldName(), "is required");
    }
    return null;
  }
}
