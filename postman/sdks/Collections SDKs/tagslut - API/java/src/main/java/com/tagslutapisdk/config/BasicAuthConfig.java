package com.tagslutapisdk.config;

import lombok.Builder;
import lombok.Data;

/**
 * Configuration for HTTP Basic authentication.
 * Stores username and password credentials that will be Base64-encoded in the Authorization header.
 */
@Builder
@Data
public class BasicAuthConfig {

  private String username;
  private String password;
}
