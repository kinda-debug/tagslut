package com.tagslutapisdk.http.serialization;

/**
 * Serialization styles supported for query parameters in OpenAPI specifications.
 * Defines how values are encoded as URL query strings.
 */
public enum QuerySerializationStyle {
  /** Form style - ampersand-separated key-value pairs (default for query parameters) */
  FORM(SerializationStyle.FORM),
  /** Space-delimited style - values separated by spaces (encoded as %20) */
  SPACE_DELIMITED(SerializationStyle.SPACE_DELIMITED),
  /** Pipe-delimited style - values separated by pipe characters (|) */
  PIPE_DELIMITED(SerializationStyle.PIPE_DELIMITED),
  /** Deep object style - nested objects with bracket notation (obj[field]=value) */
  DEEP_OBJECT(SerializationStyle.DEEP_OBJECT);

  /** The underlying serialization style */
  public final SerializationStyle style;

  QuerySerializationStyle(SerializationStyle style) {
    this.style = style;
  }
}
