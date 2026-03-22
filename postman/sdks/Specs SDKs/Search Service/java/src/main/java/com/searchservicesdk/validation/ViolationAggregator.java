package com.searchservicesdk.validation;

import com.searchservicesdk.validation.exceptions.ValidationException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * Aggregates multiple validation violations from different validators.
 * Provides a fluent API for collecting violations and throwing a ValidationException if any exist.
 */
public class ViolationAggregator {

  List<Violation> violations = new ArrayList<>();

  /**
   * Adds an array of violations to the aggregator.
   *
   * @param <T> The type parameter (unused, for API compatibility)
   * @param violations The violations to add
   * @return This aggregator for method chaining
   */
  public <T> ViolationAggregator add(Violation[] violations) {
    this.violations.addAll(Arrays.asList(violations));
    return this;
  }

  /**
   * Returns all aggregated violations as an array.
   *
   * @return Array of all collected violations
   */
  public Violation[] aggregate() {
    return violations.toArray(new Violation[0]);
  }

  /**
   * Throws a ValidationException if any violations have been collected.
   *
   * @throws ValidationException if violations exist
   */
  public void validateAll() {
    if (!violations.isEmpty()) {
      throw new ValidationException(aggregate());
    }
  }
}
