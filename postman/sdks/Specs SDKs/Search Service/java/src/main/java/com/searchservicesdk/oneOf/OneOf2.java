package com.searchservicesdk.oneOf;

import java.util.function.Consumer;
import java.util.function.Function;

/**
 * Concrete oneOf implementation for union types with 2 possible types.
 * Represents a value that can be exactly one of 2 different types at runtime.
 * Provides type-safe pattern matching through switchCase() and match() methods.
 *
 * * @param <Type0> The type of the first possible value
 * * @param <Type1> The type of the second possible value
 * */
public class OneOf2<Type0, Type1> extends OneOf {

  private final int index;
  private final Type0 value0;
  private final Type1 value1;

  /**
   * Protected constructor for creating a oneOf instance.
   * Called by generated factory methods to construct instances with the appropriate type index.
   *
   * @param index The type index (0-1) indicating which type this instance holds
   * @param value The actual value (will be cast to the appropriate type)
   */
  @SuppressWarnings("unchecked")
  protected OneOf2(int index, Object value) {
    this.index = index;
    this.value0 = index == 0 ? (Type0) value : null;
    this.value1 = index == 1 ? (Type1) value : null;
  }

  /**
   * Pattern matching using consumers (void-returning handlers).
   * Executes the appropriate consumer based on which type this instance holds.
   *
   *	 * @param case0 Handler for Type0
   *	 * @param case1 Handler for Type1
   *	 */
  public void switchCase(Consumer<Type0> case0, Consumer<Type1> case1) {
    switch (index) {
      case 0:
        case0.accept(value0);
        break;
      case 1:
        case1.accept(value1);
        break;
      default:
        throw new IllegalStateException("Unknown index: " + index);
    }
  }

  /**
   * Pattern matching using functions (value-returning handlers).
   * Executes the appropriate function based on which type this instance holds and returns the result.
   *
   * @param <TResult> The return type of all match handlers
   *	 * @param case0 Handler for Type0 that returns TResult
   *	 * @param case1 Handler for Type1 that returns TResult
   *	 * @return The result from the matching handler
   */
  public <TResult> TResult match(Function<Type0, TResult> case0, Function<Type1, TResult> case1) {
    switch (index) {
      case 0:
        return case0.apply(value0);
      case 1:
        return case1.apply(value1);
      default:
        throw new IllegalStateException("Unknown index: " + index);
    }
  }

  /**
   * Gets the value as Type0, or null if this instance holds a different type.
   *
   * @return The value if this is Type0, otherwise null
   */
  protected Type0 getValue0() {
    return value0;
  }

  /**
   * Gets the value as Type1, or null if this instance holds a different type.
   *
   * @return The value if this is Type1, otherwise null
   */
  protected Type1 getValue1() {
    return value1;
  }

  /**
   * Gets the actual value regardless of which type it is.
   *
   * @return The underlying value as Object
   */
  @Override
  public Object getValue() {
    switch (index) {
      case 0:
        return value0;
      case 1:
        return value1;
      default:
        throw new IllegalStateException("Unknown index: " + index);
    }
  }

  /**
   * Returns a string representation of this oneOf instance.
   * Includes the type index and all possible values (with null for non-active types).
   *
   * @return String representation of the oneOf instance
   */
  @Override
  public String toString() {
    return (
      "OneOf{" +
      "index=" +
      index +
      ", " +
      "value0=" +
      (value0 != null ? value0.toString() : "null") +
      ", " +
      "value1=" +
      (value1 != null ? value1.toString() : "null") +
      '}'
    );
  }
}
