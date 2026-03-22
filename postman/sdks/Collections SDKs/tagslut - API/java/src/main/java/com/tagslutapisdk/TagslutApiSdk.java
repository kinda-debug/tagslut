package com.tagslutapisdk;

import com.tagslutapisdk.config.BasicAuthConfig;
import com.tagslutapisdk.config.TagslutApiSdkConfig;
import com.tagslutapisdk.http.Environment;
import com.tagslutapisdk.http.interceptors.DefaultHeadersInterceptor;
import com.tagslutapisdk.http.interceptors.RetryInterceptor;
import com.tagslutapisdk.services.AuthService;
import com.tagslutapisdk.services.CatalogService;
import com.tagslutapisdk.services.IdentityVerificationService;
import com.tagslutapisdk.services.MyLibraryService;
import com.tagslutapisdk.services.SearchService;
import com.tagslutapisdk.services.ValidationRunService;
import java.util.concurrent.TimeUnit;
import okhttp3.OkHttpClient;

/**
 * Main SDK client class for TagslutApiSdk.
 * Provides centralized access to all service endpoints with configurable authentication,
 * environment management, hooks, and HTTP client settings.
 */
public class TagslutApiSdk {

  public final AuthService auth;
  public final CatalogService catalog;
  public final SearchService search;
  public final MyLibraryService myLibrary;
  public final IdentityVerificationService identityVerification;
  public final ValidationRunService validationRun;

  private final TagslutApiSdkConfig config;

  /**
   * Constructs a new instance of TagslutApiSdk with default configuration.
   */
  public TagslutApiSdk() {
    // Default configs
    this(TagslutApiSdkConfig.builder().build());
  }

  /**
   * Constructs a new instance of TagslutApiSdk with custom configuration.
   * Initializes all services, HTTP client, and optional OAuth token manager.
   *
   * @param config The SDK configuration including base URL, authentication, timeout, and retry settings
   */
  public TagslutApiSdk(TagslutApiSdkConfig config) {
    this.config = config;

    final OkHttpClient httpClient = new OkHttpClient.Builder()
      .addInterceptor(new DefaultHeadersInterceptor(config))
      .addInterceptor(new RetryInterceptor(config.getRetryConfig()))
      .readTimeout(config.getTimeout(), TimeUnit.MILLISECONDS)
      .build();

    this.auth = new AuthService(httpClient, config);
    this.catalog = new CatalogService(httpClient, config);
    this.search = new SearchService(httpClient, config);
    this.myLibrary = new MyLibraryService(httpClient, config);
    this.identityVerification = new IdentityVerificationService(httpClient, config);
    this.validationRun = new ValidationRunService(httpClient, config);
  }

  /**
   * Sets the environment for all API requests.
   *
   * @param environment The environment to use (e.g., DEFAULT, PRODUCTION, STAGING)
   */
  public void setEnvironment(Environment environment) {
    setBaseUrl(environment.getUrl());
  }

  /**
   * Sets the base URL for all API requests.
   *
   * @param baseUrl The base URL to use for API requests
   */
  public void setBaseUrl(String baseUrl) {
    this.config.setBaseUrl(baseUrl);
  }

  /**
   * Sets the Basic authentication credentials for all API requests.
   *
   * @param username The username for Basic authentication
   * @param password The password for Basic authentication
   */
  public void setBasicAuthCredentials(String username, String password) {
    BasicAuthConfig basicAuthConfig = this.config.getBasicAuthConfig();
    basicAuthConfig.setUsername(username);
    basicAuthConfig.setPassword(password);
  }

  /**
   * Sets the access token (Bearer token) for all API requests.
   *
   * @param token The access token to use for authentication
   */
  public void setAccessToken(String token) {
    this.config.setAccessToken(token);
  }
}
// c029837e0e474b76bc487506e8799df5e3335891efe4fb02bda7a1441840310c
