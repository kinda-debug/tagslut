package com.searchservicesdk.models;

import com.fasterxml.jackson.databind.annotation.JsonDeserialize;
import com.fasterxml.jackson.databind.annotation.JsonSerialize;
import com.searchservicesdk.json.OneOfJsonDeserializer;
import com.searchservicesdk.json.OneOfJsonSerializer;
import com.searchservicesdk.oneOf.OneOf2;
import java.util.List;

@JsonSerialize(using = OneOfJsonSerializer.class)
@JsonDeserialize(using = OneOfJsonDeserializer.class)
public class TracksDefaultModelGenre extends OneOf2<List<GenreModel>, GenreModel> {

  private TracksDefaultModelGenre(int index, Object value) {
    super(index, value);
  }

  public static TracksDefaultModelGenre ofListOfGenreModel(List<GenreModel> value) {
    return new TracksDefaultModelGenre(0, value);
  }

  public static TracksDefaultModelGenre ofGenreModel(GenreModel value) {
    return new TracksDefaultModelGenre(1, value);
  }

  public List<GenreModel> getListOfGenreModel() {
    return getValue0();
  }

  public GenreModel getGenreModel() {
    return getValue1();
  }
}
