package com.tagslutapisdk.http.serialization;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.tagslutapisdk.json.TypeUtils;
import java.lang.reflect.Field;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.stream.Collectors;
import lombok.SneakyThrows;
import org.openapitools.jackson.nullable.JsonNullableModule;

/**
 * Utility class for serialization helper methods.
 * Provides functions for type checking, URL encoding, and property extraction.
 */
public class Util {

  private static final ObjectMapper OBJECT_MAPPER = new ObjectMapper();

  static {
    OBJECT_MAPPER.setSerializationInclusion(JsonInclude.Include.NON_ABSENT);
    OBJECT_MAPPER.registerModule(new JsonNullableModule());
  }

  /**
   * Extracts properties from an object using JSON property names.
   * Uses Jackson annotations to determine the correct property names.
   *
   * @param value The object to extract properties from
   * @return A map of JSON property names to their values
   */
  public static Map<String, Object> getPropertiesWithJsonPropertyNames(Object value) {
    Map<String, Object> properties = OBJECT_MAPPER.convertValue(
      value,
      new TypeReference<Map<String, Object>>() {}
    );

    // Use the json property name if it exists, otherwise use the regular property name
    return properties
      .entrySet()
      .stream()
      .collect(
        Collectors.toMap(
          entry -> {
            try {
              Field field = entry.getValue().getClass().getField(entry.getKey());
              return TypeUtils.getJsonPropertyName(field);
            } catch (NoSuchFieldException e) {
              return entry.getKey();
            }
          },
          Map.Entry::getValue
        )
      );
  }

  /**
   * URL-encodes a string value using UTF-8 encoding.
   *
   * @param value The string to encode
   * @return The URL-encoded string
   */
  @SneakyThrows
  public static String urlEncode(String value) {
    return URLEncoder.encode(value, StandardCharsets.UTF_8.toString());
  }

  /**
   * Checks if a value is a primitive type (number, boolean, string, or character).
   *
   * @param value The value to check
   * @return true if the value is a primitive type, false otherwise
   */
  public static boolean isPrimitive(Object value) {
    return (
      value instanceof Long ||
      value instanceof Integer ||
      value instanceof Double ||
      value instanceof Float ||
      value instanceof Boolean ||
      value instanceof String ||
      value instanceof Character
    );
  }

  /**
   * Checks if a value is a complex object (not primitive and not iterable).
   *
   * @param value The value to check
   * @return true if the value is a complex object, false otherwise
   */
  public static boolean isObject(Object value) {
    return !isPrimitive(value) && !(value instanceof Iterable);
  }
}
