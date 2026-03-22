package com.searchservicesdk.json;

import com.fasterxml.jackson.core.JsonGenerator;
import com.fasterxml.jackson.databind.JsonSerializer;
import com.fasterxml.jackson.databind.SerializerProvider;
import com.searchservicesdk.oneOf.OneOf;
import java.io.IOException;

/**
 * Jackson serializer for oneOf polymorphic types.
 * Serializes a oneOf instance by writing its actual value to JSON.
 */
public class OneOfJsonSerializer extends JsonSerializer<OneOf> {

  /**
   * Serializes a oneOf value by extracting and serializing its underlying value.
   *
   * @param value The oneOf instance to serialize
   * @param gen The JSON generator to write to
   * @param provider The serializer provider
   * @throws IOException if an I/O error occurs during serialization
   */
  @Override
  public void serialize(OneOf value, JsonGenerator gen, SerializerProvider provider)
    throws IOException {
    gen.writeObject(value.getValue());
  }
}
