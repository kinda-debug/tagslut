package com.searchservicesdk.json;

import com.fasterxml.jackson.core.JsonParseException;
import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.ObjectCodec;
import com.fasterxml.jackson.databind.*;
import com.fasterxml.jackson.databind.deser.ContextualDeserializer;
import com.searchservicesdk.oneOf.OneOf;
import java.lang.reflect.Constructor;
import java.lang.reflect.Type;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import lombok.SneakyThrows;

/**
 * Jackson deserializer for oneOf polymorphic types.
 * Automatically determines the best matching type from the possible oneOf types
 * by analyzing the JSON structure and field matches, then constructs the appropriate oneOf instance.
 */
public class OneOfJsonDeserializer<T extends OneOf>
  extends JsonDeserializer<T>
  implements ContextualDeserializer {

  private JavaType tType;

  /**
   * Creates a contextual deserializer with type information from Jackson.
   *
   * @param ctxt Jackson deserialization context
   * @param property The property being deserialized
   * @return A configured deserializer instance
   */
  @Override
  public JsonDeserializer<?> createContextual(DeserializationContext ctxt, BeanProperty property) {
    JavaType tType = ctxt.getContextualType();
    OneOfJsonDeserializer<T> deserializer = new OneOfJsonDeserializer<>();
    deserializer.tType = tType;
    return deserializer;
  }

  /**
   * Deserializes JSON to a oneOf instance by finding the best matching type.
   * Uses TypeMatcher to determine which of the possible types best fits the JSON structure.
   *
   * @param p The JSON parser
   * @param ctxt The deserialization context
   * @return The deserialized oneOf instance, or null if no type matches
   * @throws Exception if deserialization fails
   */
  @Override
  @SneakyThrows
  @SuppressWarnings("unchecked")
  public T deserialize(JsonParser p, DeserializationContext ctxt) {
    JavaType oneOfType = tType.getSuperClass();

    JavaType[] possibleOneOfTypes = oneOfType
      .getBindings()
      .getTypeParameters()
      .toArray(new JavaType[0]);

    ObjectCodec codec = p.getCodec();
    JsonNode node = codec.readTree(p);

    int bestTypeIndex = TypeMatcher.getBestMatchingTypeIndex(node, possibleOneOfTypes);
    if (bestTypeIndex == -1) {
      return null;
    }

    JavaType bestType = possibleOneOfTypes[bestTypeIndex];
    Object deserializedValue = deserializeToType(bestType, node, codec);

    Constructor<T> constructor = (Constructor<T>) tType
      .getRawClass()
      .getDeclaredConstructor(int.class, Object.class);
    constructor.setAccessible(true);
    return constructor.newInstance(bestTypeIndex, deserializedValue);
  }

  /**
   * Deserializes a JSON node to the specified type.
   * Handles both collection types and regular objects.
   *
   * @param type The target Java type
   * @param node The JSON node to deserialize
   * @param codec The object codec for deserialization
   * @return The deserialized value
   * @throws JsonProcessingException if deserialization fails
   */
  private Object deserializeToType(JavaType type, JsonNode node, ObjectCodec codec)
    throws JsonProcessingException {
    if (type.isCollectionLikeType()) {
      return deserializeToArrayList(type, node, codec);
    }
    return codec.treeToValue(node, type.getRawClass());
  }

  /**
   * Deserializes each element to the contained type of the provided collection type.
   *
   * @param type The collection type
   * @param node The JSON array node
   * @param codec The object codec for deserialization
   * @return Deserialized ArrayList as Object type
   * @throws JsonProcessingException if deserialization fails
   */
  private Object deserializeToArrayList(JavaType type, JsonNode node, ObjectCodec codec)
    throws JsonProcessingException {
    if (!node.isArray()) {
      throw new RuntimeException("Attempted deserialization to ArrayList from non-array JsonNode");
    }

    JavaType innerType = type.containedType(0);
    List<Object> objectList = new ArrayList<>();
    Iterator<JsonNode> elements = node.elements();
    while (elements.hasNext()) {
      Object value = codec.treeToValue(elements.next(), innerType.getRawClass());
      objectList.add(value);
    }
    return TypeUtils.createGenericList(innerType.getRawClass(), objectList.toArray());
  }
}
