package com.searchservicesdk.validation.validators;

import com.searchservicesdk.validation.Violation;

/**
 * Interface for validators that check values against constraints.
 * Implementations validate specific types and return violations if validation fails.
 *
 * @param <T> The type of value to validate
 */
public interface Validator<T> {
  /**
   * Validates a value against defined constraints.
   *
   * @param value The value to validate
   * @return An array of violations if validation fails, empty array if valid
   */
  Violation[] validate(T value);
}
