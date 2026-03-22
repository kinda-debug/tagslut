package com.searchservicesdk.models;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.searchservicesdk.json.OneOfJsonDeserializer;
import com.searchservicesdk.json.OneOfJsonSerializer;
import com.searchservicesdk.oneOf.OneOf2;

@JsonSerialize(using = OneOfJsonSerializer.class)
@JsonDeserialize(using = OneOfJsonDeserializer.class)
public class Loc extends OneOf2<String, Long> {

  private Loc(int index, Object value) {
    super(index, value);
  }

  public static Loc ofString(String value) {
    return new Loc(0, value);
  }

  public static Loc ofLong(Long value) {
    return new Loc(1, value);
  }

  public String getString() {
    return getValue0();
  }

  public Long getLong() {
    return getValue1();
  }
}
