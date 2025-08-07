package com.reeve.vehicle.category.generator;

import java.io.IOException;
import java.net.URISyntaxException;
import java.net.URL;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;

/**
 * <p></p>
 *
 * @author hzn
 * @date 2025. 8. 8.
 */
public class SqlQueryGenerator {
  
  @SuppressWarnings("unchecked")
  public static void main(String[] args) throws IOException, URISyntaxException {
    ObjectMapper objectMapper = new ObjectMapper();
    URL lookupMnfcTblResource = SqlQueryGenerator.class.getResource("/classificated_vehicle.json");
    String classificatedVehicleJson = Files.readString(Path.of(lookupMnfcTblResource.toURI()));

    Map<String, ?> classificatedVehicleMap = objectMapper.readValue(classificatedVehicleJson,
        Map.class);
    Map<String, List<?>> manufacturersMap = (Map<String, List<?>>) classificatedVehicleMap.get(
        "manufacturers");
    StringBuilder manufacturersQuery = new StringBuilder();
    manufacturersQuery.append(
            "INSERT INTO manufacturers (code, english_name, korean_name, is_domestic) VALUES")
        .append("\n");
    manufacturersMap.forEach((key, value) -> {
      boolean isDomestic = "domestic".equals(key);
      List<Map<String, String>> manufacturers = (List<Map<String, String>>) value;
      for (Map<String, String> manufacturer : manufacturers) {
        manufacturersQuery.append("('").append(manufacturer.get("code")).append("', '")
            .append(manufacturer.get("english")).append("', '").append(manufacturer.get("korean"))
            .append("', ").append(isDomestic).append("),\n");
      }
    });
    manufacturersQuery.delete(manufacturersQuery.length() - 2, manufacturersQuery.length());
    manufacturersQuery.append(";");
    System.out.println(manufacturersQuery);

    List<Map<String, String>> models = (List<Map<String, String>>) classificatedVehicleMap.get(
        "models");
    StringBuilder modelsQuery = new StringBuilder();
    modelsQuery.append(
            "INSERT INTO vehicle_models (code, manufacturer_id, manufacturer_code, english_name, korean_name) VALUES")
        .append("\n");
    for (int i = 0; i < models.size(); i++) {
      Map<String, String> model = models.get(i);
      modelsQuery.append("('").append(model.get("code")).append("', (")
          .append("SELECT m.id FROM manufacturers m WHERE m.code = '")
          .append(model.get("manufacturer_code")).append("'), '")
          .append(model.get("manufacturer_code")).append("', '")
          .append(model.get("english").replace("'", "''")).append("', '")
          .append(model.get("korean")).append("')");
      if (i < models.size() - 1) {
        modelsQuery.append(",\n");
      }
      if (i == models.size() - 1) {
        modelsQuery.append(";");
      }
    }
    System.out.println(modelsQuery);
  }
}
