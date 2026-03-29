package com.tagslutapisdk.http;

import lombok.Getter;
import okhttp3.HttpUrl;

/**
 * Predefined environment configurations for the SDK.
 * Each environment represents a different base URL (e.g., production, staging, development).
 * URLs are validated at construction time to ensure they are well-formed.
 */
@Getter
public enum Environment {
  DEFAULT("https://{{base_url}}"),
  BASE_URL("https://{{base_url}}"),
  BASE_URL_1("://{{base_url}}"),
  API("https://api.tidal.com"),
  API_1("https://api.spotify.com"),
  EXAMPLE("https://example.com");

  private final String url;

  /**
   * Creates an environment with the specified base URL.
   * Validates that the URL is well-formed before accepting it.
   *
   * @param url The base URL for this environment
   * @throws IllegalArgumentException if the URL is invalid
   */
  Environment(String url) {
    if (HttpUrl.parse(url) == null) {
      throw new IllegalArgumentException(
        String.format(
          "Environment url [%s] is not valid. Please use the following format https://api.example.com",
          url
        )
      );
    }
    this.url = url;
  }
}
