package com.searchservicesdk.validation.validators;

import com.searchservicesdk.validation.Violation;
import java.util.ArrayList;
import java.util.List;

/**
 * Validator for list/array values with size and uniqueness constraints.
 * Can also validate individual items within the list using a nested validator.
 *
 * @param <T> The type of items in the list
 */
public class ListValidator<T> extends AbstractValidator<List<T>> {

  private AbstractValidator<T> itemValidator;
  private Integer minLength;
  private Integer maxLength;
  private Boolean uniqueItems;

  public ListValidator(String fieldName) {
    super(fieldName);
  }

  public ListValidator() {}

  /**
   * Sets the minimum list size constraint.
   *
   * @param minLength The minimum number of items allowed
   * @return This validator for method chaining
   */
  public ListValidator<T> minLength(Integer minLength) {
    this.minLength = minLength;
    return this;
  }

  /**
   * Sets the maximum list size constraint.
   *
   * @param maxLength The maximum number of items allowed
   * @return This validator for method chaining
   */
  public ListValidator<T> maxLength(Integer maxLength) {
    this.maxLength = maxLength;
    return this;
  }

  /**
   * Sets whether all items in the list must be unique.
   *
   * @param uniqueItems Whether items must be unique
   * @return This validator for method chaining
   */
  public ListValidator<T> uniqueItems(Boolean uniqueItems) {
    this.uniqueItems = uniqueItems;
    return this;
  }

  /**
   * Sets a validator to validate each individual item in the list.
   *
   * @param itemValidator The validator to apply to each list item
   * @return This validator for method chaining
   */
  public ListValidator<T> itemValidator(AbstractValidator<T> itemValidator) {
    this.itemValidator = itemValidator;
    return this;
  }

  /**
   * Validates a list against configured constraints including size, uniqueness, and item validation.
   *
   * @param list The list to validate
   * @return Array of violations if validation fails, empty array if valid
   */
  @Override
  public Violation[] validate(List<T> list) {
    Violation requiredViolation = validateRequired(list);
    if (requiredViolation != null) {
      return new Violation[] { requiredViolation };
    }
    if (list == null) {
      return new Violation[0];
    }

    List<Violation> violations = new ArrayList<>();

    if (minLength != null && list.size() < minLength) {
      violations.add(
        new Violation(getFieldName(), String.format("must have at least %d items", minLength))
      );
    }

    if (maxLength != null && list.size() > maxLength) {
      violations.add(
        new Violation(getFieldName(), String.format("must have at most %d items", maxLength))
      );
    }

    if (uniqueItems != null && list.stream().distinct().count() != list.size()) {
      violations.add(new Violation(getFieldName(), "must have unique items"));
    }

    if (itemValidator != null) {
      for (int i = 0; i < list.size(); i++) {
        T item = list.get(i);
        Violation[] itemViolations = itemValidator.setFieldName(String.valueOf(i)).validate(item);
        for (Violation itemViolation : itemViolations) {
          violations.add(
            new Violation(
              String.format("%s[%s]", getFieldName(), itemValidator.getFieldName()),
              itemViolation.getMessage()
            )
          );
        }
      }
    }

    return violations.toArray(new Violation[0]);
  }
}
