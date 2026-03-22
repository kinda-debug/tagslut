package com.searchservicesdk.http.serialization;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

/**
 * Utility class for serializing parameters according to OpenAPI serialization styles.
 * Supports simple, label, matrix, form, pipe-delimited, space-delimited, and deep object styles.
 * Handles primitives, strings, lists, and complex objects with proper encoding.
 */
public class Serializer {

  /**
   * Serializes a long value to a string with the specified style and encoding.
   *
   * @param key The parameter name
   * @param value The long value to serialize
   * @param style The serialization style to use
   * @param encode Whether to URL-encode the value
   * @return The serialized parameter string
   */
  public static String serialize(String key, long value, SerializationStyle style, boolean encode) {
    return serialize(key, String.valueOf(value), style, encode);
  }

  public static String serialize(
    String key,
    double value,
    SerializationStyle style,
    boolean encode
  ) {
    return serialize(key, String.valueOf(value), style, encode);
  }

  public static String serialize(
    String key,
    boolean value,
    SerializationStyle style,
    boolean encode
  ) {
    return serialize(key, String.valueOf(value), style, encode);
  }

  public static String serialize(
    String key,
    String value,
    SerializationStyle style,
    boolean encode
  ) {
    if (value == null) {
      value = "null";
    }
    String serializedValue = serializeValue(value, encode);
    switch (style) {
      case LABEL:
        return String.format(".%s", serializedValue);
      case MATRIX:
        return String.format(";%s=%s", key, serializedValue);
      case FORM:
        return String.format("%s=%s", key, serializedValue);
      default:
        return serializedValue;
    }
  }

  /**
   * Serializes any object value according to the specified serialization style.
   * Handles primitives, strings, lists, and complex objects with proper OpenAPI serialization.
   *
   * @param key The parameter name
   * @param value The value to serialize (can be primitive, String, List, or object)
   * @param style The serialization style to use (SIMPLE, LABEL, MATRIX, FORM, etc.)
   * @param explode Whether to use exploded form for arrays/objects
   * @param encode Whether to URL-encode values
   * @return The serialized parameter string
   */
  public static String serialize(
    String key,
    Object value,
    SerializationStyle style,
    boolean explode,
    boolean encode
  ) {
    if (value == null) {
      return serialize(key, "null", style, encode);
    }

    if (value instanceof Long) {
      return serialize(key, (Long) value, style, encode);
    } else if (value instanceof Double) {
      return serialize(key, (Double) value, style, encode);
    } else if (value instanceof Boolean) {
      return serialize(key, (Boolean) value, style, encode);
    } else if (value instanceof String) {
      return serialize(key, (String) value, style, encode);
    } else if (value instanceof List) {
      return serializeList(key, (List<?>) value, style, explode, encode);
    }

    return serializeObject(key, value, style, explode, encode);
  }

  private static String serializeValue(Object value, boolean encode) {
    if (value instanceof Long || value instanceof Double || value instanceof Boolean) {
      return value.toString();
    } else if (value instanceof String) {
      return encode ? Util.urlEncode((String) value) : (String) value;
    } else if (value instanceof List) {
      return serializeList("", (List<?>) value, SerializationStyle.SIMPLE, false, encode);
    }
    return serializeObject("", value, SerializationStyle.SIMPLE, false, encode);
  }

  private static String serializeList(
    String key,
    List<?> value,
    SerializationStyle style,
    boolean explode,
    boolean encode
  ) {
    if (value.isEmpty()) {
      return "";
    }

    List<String> serializedValues = value
      .stream()
      .map(v -> serializeValue(v, encode))
      .collect(Collectors.toList());
    switch (style) {
      case SIMPLE:
        return String.join(",", serializedValues);
      case LABEL:
        String separator = explode ? "." : ",";
        // .1,2,3 or .1.2.3
        return String.format(".%s", String.join(separator, serializedValues));
      case MATRIX:
        return explode
          ? serializedValues
            .stream()
            .map(v -> String.format(";%s=%s", key, v))
            .collect(Collectors.joining(""))
          : String.format(";%s=", key) + String.join(",", serializedValues);
    }

    if (explode) {
      return value
        .stream()
        .map(v -> serialize(key, v, SerializationStyle.FORM, explode, encode))
        .collect(Collectors.joining("&"));
    }

    String separator = style == SerializationStyle.PIPE_DELIMITED
      ? "%7C"
      : style == SerializationStyle.SPACE_DELIMITED ? " " : ",";
    return String.format("%s=%s", key, String.join(separator, serializedValues));
  }

  private static String serializeObject(
    String key,
    Object value,
    SerializationStyle style,
    boolean explode,
    boolean encode
  ) {
    Map<String, Object> properties = Util.getPropertiesWithJsonPropertyNames(value);

    switch (style) {
      case SIMPLE:
        return explode
          ? // key=value,key=value
          properties
            .entrySet()
            .stream()
            .map(p -> String.format("%s=%s", p.getKey(), serializeValue(p.getValue(), encode)))
            .collect(Collectors.joining(","))
          : // key=value&key=value
          properties
            .entrySet()
            .stream()
            .map(p -> String.format("%s,%s", p.getKey(), serializeValue(p.getValue(), encode)))
            .collect(Collectors.joining(","));
      case LABEL:
        return explode
          ? // .key=value.key=value
          properties
            .entrySet()
            .stream()
            .map(p -> String.format(".%s=%s", p.getKey(), serializeValue(p.getValue(), encode)))
            .collect(Collectors.joining())
          : // .id=key,value,key,value
          String.format(
            ".%s=%s",
            key,
            properties
              .entrySet()
              .stream()
              .map(p -> String.format("%s,%s", p.getKey(), serializeValue(p.getValue(), encode)))
              .collect(Collectors.joining(","))
          );
      case MATRIX:
        return explode
          ? // .key=value.key=value
          properties
            .entrySet()
            .stream()
            .map(p -> String.format(";%s=%s", p.getKey(), serializeValue(p.getValue(), encode)))
            .collect(Collectors.joining())
          : // .id=key,value,key,value
          String.format(
            ";%s=%s",
            key,
            properties
              .entrySet()
              .stream()
              .map(p -> String.format("%s,%s", p.getKey(), serializeValue(p.getValue(), encode)))
              .collect(Collectors.joining(","))
          );
      case DEEP_OBJECT:
        return serializeDeepObject(key, value, true, encode);
      default:
        // Form style
        // key=value&key=value
        return explode
          ? properties
            .entrySet()
            .stream()
            .map(p -> String.format("%s=%s", p.getKey(), serializeValue(p.getValue(), encode)))
            .collect(Collectors.joining("&"))
          : key +
          "=" +
          properties
            .entrySet()
            .stream()
            .map(p -> String.format("%s,%s", p.getKey(), serializeValue(p.getValue(), encode)))
            .collect(Collectors.joining(","));
    }
  }

  /**
   * Serializes an object using deep object style (e.g., id[key]=value&id[key][deepKey]=deepValue).
   * Recursively handles nested objects with bracket notation.
   *
   * @param key The parameter name
   * @param value The value to serialize
   * @param topLevel Whether this is the top-level call (affects bracket notation)
   * @param encode Whether to URL-encode values
   * @return The serialized deep object string
   */
  public static String serializeDeepObject(
    String key,
    Object value,
    boolean topLevel,
    boolean encode
  ) {
    if (!Util.isObject(value)) {
      return String.format("[%s]=%s", key, serializeValue(value, encode));
    }

    Map<String, Object> properties = Util.getPropertiesWithJsonPropertyNames(value);

    // id[key]=value&id[key][deepKey]=deepValue
    return properties
      .entrySet()
      .stream()
      .map(p ->
        String.format(
          "%s%s",
          topLevel ? key : String.format("[%s]", key),
          serializeDeepObject(p.getKey(), p.getValue(), false, encode)
        )
      )
      .collect(Collectors.joining("&"));
  }
}
