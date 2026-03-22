package com.searchservicesdk.exceptions;

import com.searchservicesdk.models.Loc;
import lombok.Getter;
import okhttp3.Response;

/**
 * Exception class for API errors with structured Loc error details.
 * Extends ApiError to provide typed access to the error response model.
 * Thrown when the API returns an error response that can be deserialized to Loc.
 */
@Getter
public class LocException extends ApiError {

  /** The structured error details from the API response */
  private final Loc error;

  /**
   * Creates a new exception with structured error details.
   *
   * @param error The deserialized error model
   * @param message The error message
   * @param code The HTTP status code
   * @param response The raw HTTP response
   */
  public LocException(Loc error, String message, int code, Response response) {
    super(message, code, response);
    this.error = error;
  }
}
