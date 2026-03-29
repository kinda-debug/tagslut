package com.tagslutapisdk.json;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.lang.reflect.Field;
import java.util.ArrayList;
import java.util.List;

/**
 * Utility methods for type handling and reflection operations in JSON serialization.
 * Provides helpers for extracting JSON property names and creating generic lists.
 */
public class TypeUtils {

  /**
   * Extracts the JSON property name from a field, using the @JsonProperty annotation if present.
   *
   * @param type The field to extract the name from
   * @return The JSON property name (from annotation) or the field name
   */
  public static String getJsonPropertyName(Field type) {
    JsonProperty annotation = type.getAnnotation(JsonProperty.class);
    if (annotation != null) {
      return annotation.value();
    }
    return type.getName();
  }

  /**
   * Creates a generic list with type safety from an array of objects.
   * Used for deserializing JSON arrays to strongly-typed Java lists.
   *
   * @param <Type> The element type of the list
   * @param type The class of the element type
   * @param params The objects to add to the list
   * @return A typed list containing the provided elements
   */
  public static <Type> List<Type> createGenericList(Class<Type> type, Object... params) {
    List<Type> list = new ArrayList<>();
    for (Object param : params) {
      list.add((Type) param);
    }
    return list;
  }
}
