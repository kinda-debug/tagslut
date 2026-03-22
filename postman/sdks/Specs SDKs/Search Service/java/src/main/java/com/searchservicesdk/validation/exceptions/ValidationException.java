package com.searchservicesdk.validation.exceptions;

import com.searchservicesdk.validation.Violation;
import lombok.Getter;

/**
 * Exception thrown when validation constraints are violated.
 * Contains all validation violations that occurred during validation.
 */
public class ValidationException extends RuntimeException {

  @Getter
  private final Violation[] violations;

  /**
   * Constructs a new ValidationException with the specified violations.
   *
   * @param violations The array of validation violations that occurred
   */
  public ValidationException(Violation[] violations) {
    super();
    this.violations = violations;
  }

  /**
   * Returns a formatted message describing all validation violations.
   *
   * @return A message listing all violations with their paths and messages
   */
  @Override
  public String getMessage() {
    return "Validation failed with the following violations: " + this.buildViolationsString();
  }

  /**
   * Builds a formatted string containing all violations.
   *
   * @return A newline-separated string of all violations
   */
  private String buildViolationsString() {
    StringBuilder sb = new StringBuilder();
    for (Violation violation : this.violations) {
      sb.append(violation.toString()).append("\n");
    }
    return sb.toString();
  }
}
