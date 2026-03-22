package com.searchservicesdk.http;

import lombok.Getter;
import lombok.RequiredArgsConstructor;

/**
 * Enum representing HTTP methods (verbs) used in API requests.
 * Provides utility methods for determining method characteristics.
 */
@Getter
@RequiredArgsConstructor
public enum HttpMethod {
  /** HTTP GET method for retrieving resources */
  GET("GET"),
  /** HTTP POST method for creating resources */
  POST("POST"),
  /** HTTP PUT method for updating/replacing resources */
  PUT("PUT"),
  /** HTTP PATCH method for partially updating resources */
  PATCH("PATCH"),
  /** HTTP DELETE method for removing resources */
  DELETE("DELETE"),
  /** HTTP HEAD method for retrieving headers only */
  HEAD("HEAD"),
  /** HTTP OPTIONS method for describing communication options */
  OPTIONS("OPTIONS"),
  /** HTTP TRACE method for diagnostic purposes */
  TRACE("TRACE"),
  /** HTTP CONNECT method for establishing tunnels */
  CONNECT("CONNECT");

  private final String method;

  /**
   * Determines if this HTTP method requires a request body.
   *
   * @return true if POST, PUT, or PATCH; false otherwise
   */
  public boolean requiresRequestBody() {
    return method.equals("POST") || method.equals("PUT") || method.equals("PATCH");
  }
}
