package com.reeve.vehicle.category.generator;

import java.io.IOException;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * <p></p>
 *
 * @author hzn
 * @date 2025. 8. 8.
 */
public class ClassificationProcessor {

  @SuppressWarnings("unchecked")
  public static void main(String[] args) throws IOException, URISyntaxException {
    ObjectMapper mapper = new ObjectMapper();
    URL lookupMnfcTblResource = ClassificationProcessor.class.getResource("/lookupMnfcTbl.json");
    String lookupMnfcTbl = Files.readString(Path.of(lookupMnfcTblResource.toURI()));
    URL lookupMdlGrpTblResource = ClassificationProcessor.class.getResource(
        "/lookupMdlGrpTbl.json");
    String lookupMdlGrpTbl = Files.readString(Path.of(lookupMdlGrpTblResource.toURI()));

    Map<String, Object> result = new HashMap<>();
    // 제조사 분류
    Map<String, String> brandMap = mapper.readValue(lookupMnfcTbl, Map.class);
    List<Map<String, String>> domesticBrandList = brandMap.entrySet().stream().filter(
            entry -> List.of("현대", "기아", "쉐보레(GM대우)", "쌍용", "르노삼성", "제네시스").contains(entry.getKey()))
        .map(entry -> {
          Map<String, String> domestic = new HashMap<>();
          String english = entry.getValue();
          domestic.put("code",
              english.toLowerCase().replaceAll("[\\s-(]+", "_").replaceAll("[')]+", ""));
          domestic.put("korean", entry.getKey());
          domestic.put("english", english);
          return domestic;
        }).toList();
    List<Map<String, String>> importedBrandList = brandMap.entrySet().stream().filter(
            entry -> !List.of("현대", "기아", "쉐보레(GM대우)", "쌍용", "르노삼성", "제네시스").contains(entry.getKey()))
        .map(entry -> {
          Map<String, String> imported = new HashMap<>();
          String english = entry.getValue();
          imported.put("code",
              english.toLowerCase().replaceAll("[\\s-(]+", "_").replaceAll("[')]+", ""));
          imported.put("korean", entry.getKey());
          imported.put("english", english);
          return imported;
        }).toList();
    Map<String, List<Map<String, String>>> manufacturers = new HashMap<>();
    manufacturers.put("domestic", domesticBrandList);
    manufacturers.put("imported", importedBrandList);
    result.put("manufacturers", manufacturers);

    // 모델 분류
    Map<String, String> modelGroupMap = mapper.readValue(lookupMdlGrpTbl, Map.class);
    List<Map<String, String>> allManufacturers = Stream.concat(
        manufacturers.get("domestic").stream(), manufacturers.get("imported").stream()).toList();
    List<Map<String, String>> modelList = modelGroupMap.entrySet().stream().map(entry -> {
      String modelGroup = entry.getKey();
      String modelKorean = modelGroup.split("_")[1];
      String modelEnglish = entry.getValue();
      String manufacturerCode = allManufacturers.stream()
          .filter(m -> modelGroup.contains(m.get("korean"))).findFirst().get().get("code");
      Map<String, String> model = new HashMap<>();
      model.put("manufacturer_code", manufacturerCode);
      model.put("code",
          modelEnglish.toLowerCase().replaceAll("[\\s-(]+", "_").replaceAll("[')]+", ""));
      model.put("korean", modelKorean);
      model.put("english", modelEnglish);
      return model;
    }).toList();
    result.put("models", modelList);

    // 최종 결과
    System.out.println(mapper.writeValueAsString(result));
  }
}
