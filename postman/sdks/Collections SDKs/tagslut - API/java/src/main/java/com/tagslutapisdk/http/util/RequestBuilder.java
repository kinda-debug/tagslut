package com.tagslutapisdk.http.util;

import com.tagslutapisdk.config.BasicAuthConfig;
import com.tagslutapisdk.http.HttpMethod;
import com.tagslutapisdk.http.ModelConverter;
import com.tagslutapisdk.http.serialization.PathSerializationStyle;
import com.tagslutapisdk.http.serialization.QuerySerializationStyle;
import com.tagslutapisdk.http.serialization.SerializationStyle;
import com.tagslutapisdk.http.serialization.Serializer;
import java.util.*;
import lombok.NonNull;
import okhttp3.HttpUrl;
import okhttp3.MediaType;
import okhttp3.Request;
import okhttp3.RequestBody;
import org.jetbrains.annotations.NotNull;

/**
 * Fluent builder for constructing OkHttp Request objects with SDK-specific features.
 * Handles path/query parameter serialization, header management, authentication,
 * and request body construction according to OpenAPI serialization styles.
 */
public class RequestBuilder {

  @NonNull
  private final String baseUrl;

  @NonNull
  private final String path;

  @NonNull
  private final HttpMethod httpMethod;

  private final HashMap<String, String> pathParameters = new HashMap<>();

  private final List<String> queryParameters = new ArrayList<>();

  private final HashMap<String, String> headers = new HashMap<>();

  private RequestBody body;

  /**
   * Initializes a new instance of {@code RequestBuilder}.
   *
   * @param path The path template to use for the request. Should have path parameters as
   *     placeholders surrounded by brackets (Eg. "/users/{id}", where "id" is a path parameter).
   */
  public RequestBuilder(
    @NotNull HttpMethod httpMethod,
    @NotNull String baseUrl,
    @NotNull String path
  ) {
    this.httpMethod = httpMethod;
    this.baseUrl = baseUrl;
    this.path = path;
  }

  /**
   * Sets a path parameter using the default SIMPLE serialization style.
   * If the parameter is not present in the URL template, it will be ignored.
   *
   * @param key The path parameter name
   * @param value The parameter value
   * @return This builder instance for chaining
   */
  public RequestBuilder setPathParameter(@NonNull String key, @NonNull Object value) {
    return setPathParameter(key, value, PathSerializationStyle.SIMPLE, false);
  }

  /**
   * Sets a path parameter with custom serialization style and explode option.
   * If the parameter is not present in the URL template, it will be ignored.
   *
   * @param key The path parameter name
   * @param value The parameter value
   * @param style The serialization style to use
   * @param explode Whether to explode arrays/objects into separate values
   * @return This builder instance for chaining
   */
  public RequestBuilder setPathParameter(
    @NonNull String key,
    @NonNull Object value,
    PathSerializationStyle style,
    boolean explode
  ) {
    String serializedValue = Serializer.serialize(key, value, style.style, explode, true);
    pathParameters.put(key, serializedValue);
    return this;
  }

  /**
   * Sets a query parameter using the default FORM serialization style with explode enabled.
   *
   * @param key The query parameter name
   * @param value The parameter value
   * @return This builder instance for chaining
   */
  public RequestBuilder setQueryParameter(@NonNull String key, @NonNull Object value) {
    return setQueryParameter(key, value, QuerySerializationStyle.FORM, true);
  }

  /**
   * Sets a query parameter with custom serialization style and explode option.
   *
   * @param key The query parameter name
   * @param value The parameter value
   * @param style The serialization style to use
   * @param explode Whether to explode arrays/objects into separate parameters
   * @return This builder instance for chaining
   */
  public RequestBuilder setQueryParameter(
    @NonNull String key,
    @NonNull Object value,
    QuerySerializationStyle style,
    boolean explode
  ) {
    String serializedValue = Serializer.serialize(key, value, style.style, explode, true);
    queryParameters.add(serializedValue);
    return this;
  }

  /**
   * Sets a query parameter using the default FORM style if the value is not null.
   *
   * @param key The query parameter name
   * @param value The parameter value (ignored if null)
   * @return This builder instance for chaining
   */
  public RequestBuilder setOptionalQueryParameter(@NonNull String key, Object value) {
    return setOptionalQueryParameter(key, value, QuerySerializationStyle.FORM, true);
  }

  /**
   * Sets a query parameter with custom serialization if the value is not null.
   *
   * @param key The query parameter name
   * @param value The parameter value (ignored if null)
   * @param style The serialization style to use
   * @param explode Whether to explode arrays/objects into separate parameters
   * @return This builder instance for chaining
   */
  public RequestBuilder setOptionalQueryParameter(
    @NonNull String key,
    Object value,
    QuerySerializationStyle style,
    boolean explode
  ) {
    if (value != null) {
      return setQueryParameter(key, value, style, explode);
    }
    return this;
  }

  /**
   * Sets a header using SIMPLE serialization style without explode.
   *
   * @param key The header name
   * @param value The header value
   * @return This builder instance for chaining
   */
  public RequestBuilder setHeader(@NonNull String key, @NonNull Object value) {
    return setHeader(key, value, false);
  }

  /**
   * Sets a header using SIMPLE serialization style with custom explode option.
   *
   * @param key The header name
   * @param value The header value
   * @param explode Whether to explode arrays/objects
   * @return This builder instance for chaining
   */
  public RequestBuilder setHeader(@NonNull String key, @NonNull Object value, boolean explode) {
    String serializedValue = Serializer.serialize(
      key,
      value,
      SerializationStyle.SIMPLE,
      explode,
      false
    );
    headers.put(key, serializedValue);
    return this;
  }

  /**
   * Sets a header if the value is not null, using SIMPLE style without explode.
   *
   * @param key The header name
   * @param value The header value (ignored if null)
   * @return This builder instance for chaining
   */
  public RequestBuilder setOptionalHeader(@NonNull String key, Object value) {
    return setOptionalHeader(key, value, false);
  }

  /**
   * Sets a header if the value is not null, with custom explode option.
   *
   * @param key The header name
   * @param value The header value (ignored if null)
   * @param explode Whether to explode arrays/objects
   * @return This builder instance for chaining
   */
  public RequestBuilder setOptionalHeader(@NonNull String key, Object value, boolean explode) {
    if (value != null) {
      return setHeader(key, value, explode);
    }
    return this;
  }

  /**
   * Sets the raw request body.
   *
   * @param body The request body
   * @return This builder instance for chaining
   */
  public RequestBuilder setBody(RequestBody body) {
    this.body = body;
    return this;
  }

  /**
   * Sets the request body as JSON using the default application/json media type.
   *
   * @param content The object to serialize as JSON
   * @return This builder instance for chaining
   */
  public RequestBuilder setJsonContent(Object content) {
    return setJsonContent(content, MediaType.parse("application/json; charset=utf-8"));
  }

  /**
   * Sets the request body as JSON with a custom media type.
   *
   * @param content The object to serialize as JSON
   * @param mediaType The media type to use
   * @return This builder instance for chaining
   */
  public RequestBuilder setJsonContent(Object content, MediaType mediaType) {
    if (content == null) {
      return this;
    }
    setBody(
      RequestBody.create(Objects.requireNonNull(ModelConverter.modelToJson(content)), mediaType)
    );
    return this;
  }

  /**
   * Sets the access token authentication header with a "Bearer" prefix.
   *
   * @param token The access token
   * @return This builder instance for chaining
   */
  public RequestBuilder setAccessTokenAuth(String token) {
    if (token == null) {
      return this;
    }
    return setAccessTokenAuth(token, "Bearer");
  }

  /**
   * Sets the access token authentication header with a custom prefix.
   *
   * @param token The access token
   * @param prefix The authorization prefix (e.g., "Bearer", "Token")
   * @return This builder instance for chaining
   */
  public RequestBuilder setAccessTokenAuth(String token, String prefix) {
    if (token == null || prefix == null) {
      return this;
    }
    return setHeader("Authorization", String.format("%s %s", prefix, token));
  }

  /**
   * Sets the basic authentication header from configuration.
   * Encodes username:password as Base64 and adds to Authorization header.
   *
   * @param config The basic auth configuration
   * @return This builder instance for chaining
   */
  public RequestBuilder setBasicAuth(BasicAuthConfig config) {
    if (config == null || config.getUsername() == null || config.getPassword() == null) {
      return this;
    }
    String credentials = String.format("%s:%s", config.getUsername(), config.getPassword());
    String basicAuth = "Basic " + Base64.getEncoder().encodeToString(credentials.getBytes());
    return setHeader("Authorization", basicAuth);
  }

  /**
   * Builds and returns the configured OkHttp Request instance.
   * Applies all path parameters, query parameters, headers, and body to create the final request.
   *
   * @return The configured Request instance ready to execute
   */
  public Request build() {
    String url = buildUrl();
    Request.Builder requestBuilder = new Request.Builder().url(url);

    for (Map.Entry<String, String> entry : headers.entrySet()) {
      requestBuilder.addHeader(entry.getKey(), entry.getValue());
    }

    if (httpMethod.requiresRequestBody() && this.body == null) {
      this.body = RequestBody.create(new byte[0]);
    }

    requestBuilder.method(httpMethod.getMethod(), body);

    return requestBuilder.build();
  }

  /**
   * Constructs the full URL by combining base URL, path, path parameters, and query parameters.
   *
   * @return The complete URL string
   */
  private String buildUrl() {
    String path = this.path;

    for (Map.Entry<String, String> entry : pathParameters.entrySet()) {
      String key = entry.getKey();
      String value = entry.getValue();
      path = path.replace("{" + key + "}", value);
    }

    String url = Objects.requireNonNull(HttpUrl.parse(baseUrl))
      .newBuilder()
      .addPathSegments(path)
      .build()
      .toString();

    if (!queryParameters.isEmpty()) {
      url += "?" + String.join("&", queryParameters);
    }

    return url;
  }
}
