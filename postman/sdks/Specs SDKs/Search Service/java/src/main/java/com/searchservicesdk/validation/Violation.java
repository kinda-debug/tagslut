package com.searchservicesdk.validation;

/**
 * Represents a validation constraint violation.
 * Contains the path to the violating field and a descriptive error message.
 */
public class Violation {

  private final String path;
  private final String message;

  /**
   * Constructs a new Violation.
   *
   * @param path The JSON path to the field that violated the constraint
   * @param message The descriptive error message
   */
  public Violation(String path, String message) {
    this.path = path;
    this.message = message;
  }

  /**
   * Gets the path to the violating field.
   *
   * @return The JSON path (e.g., "user.email")
   */
  public String getPath() {
    return path;
  }

  /**
   * Gets the error message describing the violation.
   *
   * @return The error message
   */
  public String getMessage() {
    return message;
  }

  /**
   * Returns a string representation of the violation in the format "path: message".
   *
   * @return The formatted violation string
   */
  @Override
  public String toString() {
    return String.format("%s: %s", path, message);
  }
}
