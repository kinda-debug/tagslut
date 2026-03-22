package com.searchservicesdk.models;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.searchservicesdk.json.OneOfJsonDeserializer;
import com.searchservicesdk.json.OneOfJsonSerializer;
import com.searchservicesdk.oneOf.OneOf2;
import java.util.List;

@JsonSerialize(using = OneOfJsonSerializer.class)
@JsonDeserialize(using = OneOfJsonDeserializer.class)
public class ReleasesDefaultModelGenre extends OneOf2<List<GenreModel>, GenreModel> {

  private ReleasesDefaultModelGenre(int index, Object value) {
    super(index, value);
  }

  public static ReleasesDefaultModelGenre ofListOfGenreModel(List<GenreModel> value) {
    return new ReleasesDefaultModelGenre(0, value);
  }

  public static ReleasesDefaultModelGenre ofGenreModel(GenreModel value) {
    return new ReleasesDefaultModelGenre(1, value);
  }

  public List<GenreModel> getListOfGenreModel() {
    return getValue0();
  }

  public GenreModel getGenreModel() {
    return getValue1();
  }
}
