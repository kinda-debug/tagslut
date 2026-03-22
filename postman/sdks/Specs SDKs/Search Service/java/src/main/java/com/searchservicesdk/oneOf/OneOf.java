package com.searchservicesdk.oneOf;

/**
 * Abstract base class for oneOf polymorphic types.
 * OneOf types represent a value that can be one of several possible types (union types).
 * Subclasses provide type-safe access to the actual value.
 */
public abstract class OneOf {

  /**
   * Gets the actual value contained in this oneOf instance.
   *
   * @return The underlying value (type varies by concrete oneOf implementation)
   */
  public abstract Object getValue();
}
