package com.searchservicesdk.json;

import com.fasterxml.jackson.databind.JavaType;
import com.fasterxml.jackson.databind.JsonNode;
import java.lang.reflect.Type;
import java.util.Arrays;
import java.util.HashMap;
import java.util.Iterator;

/**
 * Utility for matching JSON structures to Java types in oneOf polymorphic scenarios.
 * Analyzes JSON nodes to determine the best matching type from a set of possible types
 * by examining structure (object/array/primitive) and field matches.
 */
public class TypeMatcher {

  /**
   * Determines the best matching type index for a JSON node from possible types.
   * Routes to specialized matching logic based on the JSON node type.
   *
   * @param node The JSON node to match
   * @param possibleTypes Array of possible Java types
   * @return The index of the best matching type, or -1 if no match found
   */
  public static int getBestMatchingTypeIndex(JsonNode node, JavaType[] possibleTypes) {
    if (node.isNull()) {
      return -1;
    }

    if (node.isObject()) {
      return getBestMatchingObjectTypeIndex(node, possibleTypes);
    }

    if (node.isArray()) {
      return getBestMatchingArrayTypeIndex(node, possibleTypes);
    }

    return getBestMatchingPrimitive(node, possibleTypes);
  }

  /**
   * Finds the best matching object type by counting field matches.
   * Returns the type with the highest number of matching fields.
   *
   * @param node The JSON object node
   * @param possibleTypes Array of possible Java types
   * @return The index of the best matching type
   */
  private static int getBestMatchingObjectTypeIndex(JsonNode node, JavaType[] possibleTypes) {
    int highestMatchCount = 0;
    int bestMatchIndex = -1;
    for (int i = 0; i < possibleTypes.length; i++) {
      JavaType type = possibleTypes[i];
      if (type.isCollectionLikeType() || type.isPrimitive()) {
        continue;
      }
      int matchCount = getPropertyMatchCount(node, type.getRawClass());
      if (matchCount > highestMatchCount) {
        highestMatchCount = matchCount;
        bestMatchIndex = i;
      }
    }
    return bestMatchIndex;
  }

  /**
   * Counts how many JSON fields match the declared fields in a Java class.
   *
   * @param node The JSON object node
   * @param type The Java class to match against
   * @return The number of matching fields
   */
  private static int getPropertyMatchCount(JsonNode node, Class<?> type) {
    int matchCount = 0;
    String[] typeFields = Arrays.stream(type.getDeclaredFields())
      .map(TypeUtils::getJsonPropertyName)
      .toArray(String[]::new);

    for (Iterator<String> it = node.fieldNames(); it.hasNext();) {
      String jsonField = it.next();
      if (Arrays.asList(typeFields).contains(jsonField)) {
        matchCount++;
      }
    }
    return matchCount;
  }

  /**
   * Finds the best matching primitive type for a JSON primitive value.
   * Handles string, numeric (int/long/double/float), and boolean types.
   *
   * @param node The JSON primitive node
   * @param possibleTypes Array of possible Java types
   * @return The index of the best matching type
   */
  private static int getBestMatchingPrimitive(JsonNode node, JavaType[] possibleTypes) {
    Type bestMatch = null;

    if (node.isTextual()) {
      bestMatch = Arrays.stream(possibleTypes)
        .filter(t -> t.getRawClass() == String.class)
        .findFirst()
        .orElse(null);
    }

    if (node.isNumber()) {
      if (node.canConvertToInt() || node.canConvertToLong()) {
        bestMatch = Arrays.stream(possibleTypes)
          .filter(t -> t.getRawClass() == Long.class || t.getRawClass() == Integer.class)
          .findFirst()
          .orElse(null);
      }

      if (node.isFloatingPointNumber()) {
        Type floatType = Arrays.stream(possibleTypes)
          .filter(t -> t.getRawClass() == Double.class || t.getRawClass() == Float.class)
          .findFirst()
          .orElse(null);
        if (floatType != null) {
          // Overwrites int/long
          bestMatch = floatType;
        }
      }
    }

    if (node.isBoolean()) {
      bestMatch = Arrays.stream(possibleTypes)
        .filter(t -> t.getRawClass() == Boolean.class)
        .findFirst()
        .orElse(null);
    }

    return Arrays.asList(possibleTypes).indexOf(bestMatch);
  }

  /**
   * Finds the best matching array/collection type by matching the first element.
   * Uses recursive type matching on the first array element to determine the best collection type.
   *
   * @param node The JSON array node
   * @param possibleTypes Array of possible Java types
   * @return The index of the best matching collection type
   */
  private static int getBestMatchingArrayTypeIndex(JsonNode node, JavaType[] possibleTypes) {
    HashMap<JavaType, Integer> typeToIndexMap = new HashMap<>();

    for (int i = 0; i < possibleTypes.length; i++) {
      JavaType type = possibleTypes[i];
      if (!type.isCollectionLikeType()) {
        continue;
      }

      if (!node.elements().hasNext()) {
        return i;
      }

      JavaType innerType = type.containedType(0);
      typeToIndexMap.put(innerType, i);
    }

    // Match best type match for first element in array
    JsonNode firstElement = node.elements().next();

    JavaType[] innerTypes = typeToIndexMap.keySet().toArray(new JavaType[0]);
    int bestInnerTypeMatchIndex = getBestMatchingTypeIndex(firstElement, innerTypes);

    return typeToIndexMap.get(innerTypes[bestInnerTypeMatchIndex]);
  }
}
