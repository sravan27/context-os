use serde_json::Value;

use crate::{
    append_missing_protected_context, build_result, fail_open, ProtectionRules, ProvenanceNote,
    Reducer, ReducerKind, ReductionMode, RiskLevel,
};

pub struct JsonReducer;

impl Reducer for JsonReducer {
    fn kind(&self) -> ReducerKind {
        ReducerKind::Json
    }

    fn detect(&self, input: &str) -> f32 {
        if serde_json::from_str::<Value>(input).is_ok() {
            0.95
        } else {
            0.0
        }
    }

    fn reduce(
        &self,
        input: &str,
        mode: ReductionMode,
        protections: &ProtectionRules,
    ) -> crate::ReductionResult {
        let confidence = self.detect(input);
        if confidence == 0.0 {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Medium,
                confidence,
                input,
                "Input was not valid JSON",
            );
        }

        let Ok(value) = serde_json::from_str::<Value>(input) else {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Medium,
                confidence,
                input,
                "JSON parsing failed; original content preserved",
            );
        };

        // Only bail on very small JSON
        if input.lines().count() < 4 && input.len() < 200 {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Medium,
                confidence,
                input,
                "JSON input already concise; original content preserved",
            );
        }

        let reduced = compact_value(&value, 0);
        let reduced = append_missing_protected_context(input, &reduced, protections);

        let result = build_result(
            self.kind(),
            mode,
            RiskLevel::Medium,
            confidence,
            input,
            reduced,
            "Compacted JSON: deduplicated array items, inlined small values, sampled large arrays"
                .to_string(),
            vec![ProvenanceNote {
                reason: "structured-compact".to_string(),
                detail: "JSON was compacted using deduplication and sampling while preserving protected values".to_string(),
            }],
        );

        if result.metadata.transformed
            && result.metadata.after_tokens >= result.metadata.before_tokens
        {
            return fail_open(
                self.kind(),
                mode,
                RiskLevel::Medium,
                confidence,
                input,
                "Safe reduction did not lower the estimated token count; original JSON preserved",
            );
        }

        result
    }
}

/// Produce a compact text representation of a JSON value.
/// Strategy:
/// - Small scalars inline on one line
/// - Arrays: deduplicate identical items, sample first item + count
/// - Objects: compact key: value pairs
fn compact_value(value: &Value, depth: usize) -> String {
    let indent = "  ".repeat(depth);
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => {
            if s.len() <= 80 {
                format!("{s:?}")
            } else {
                let preview: String = s.chars().take(80).collect();
                format!("{preview:?}...(len={})", s.len())
            }
        }
        Value::Array(items) if items.is_empty() => "[]".to_string(),
        Value::Array(items) => compact_array(items, depth),
        Value::Object(map) if map.is_empty() => "{}".to_string(),
        Value::Object(map) => {
            let mut lines = vec![format!("{indent}{{")];
            for (key, val) in map {
                let val_str = compact_value(val, depth + 1);
                if val_str.contains('\n') {
                    lines.push(format!("{indent}  {key:?}:"));
                    lines.push(val_str);
                } else {
                    lines.push(format!("{indent}  {key:?}: {val_str}"));
                }
            }
            lines.push(format!("{indent}}}"));
            lines.join("\n")
        }
    }
}

fn compact_array(items: &[Value], depth: usize) -> String {
    let indent = "  ".repeat(depth);

    // Deduplicate: group identical serialized items
    let mut unique: Vec<(&Value, usize)> = Vec::new();
    for item in items {
        if let Some(entry) = unique.iter_mut().find(|(v, _)| *v == item) {
            entry.1 += 1;
        } else {
            unique.push((item, 1));
        }
    }

    // If all items are identical, show one sample + total count
    if unique.len() == 1 {
        let sample = compact_value(unique[0].0, depth + 1);
        if items.len() == 1 {
            return format!("{indent}[{sample}]");
        }
        let mut lines = vec![format!("{indent}array(len={}, all identical):", items.len())];
        lines.push(format!("{indent}  sample: {sample}"));
        return lines.join("\n");
    }

    // Show unique items with counts, sample up to 3
    let mut lines = vec![format!(
        "{indent}array(len={}, {} unique):",
        items.len(),
        unique.len()
    )];
    for (i, (val, count)) in unique.iter().enumerate() {
        if i >= 3 {
            let remaining: usize = unique[i..].iter().map(|(_, c)| c).sum();
            lines.push(format!(
                "{indent}  ...and {} more unique items ({} total entries)",
                unique.len() - i,
                remaining
            ));
            break;
        }
        let val_str = compact_value(val, depth + 1);
        if *count > 1 {
            lines.push(format!("{indent}  (x{count}) {val_str}"));
        } else {
            lines.push(format!("{indent}  {val_str}"));
        }
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    const FIXTURE: &str = include_str!(concat!(
        env!("CARGO_MANIFEST_DIR"),
        "/../../tests/fixtures/large-response.json"
    ));

    #[test]
    fn summarizes_large_json_and_preserves_versions() {
        let protections = ProtectionRules {
            protected_literals: vec!["req_9HX".to_string()],
            ..ProtectionRules::safe_defaults()
        };
        let reducer = JsonReducer;
        let result = reducer.reduce(FIXTURE, ReductionMode::Safe, &protections);
        assert!(result.output.contains("req_9HX"));
        assert!(result.output.contains("v2026.04.1"));
        assert!(result
            .output
            .contains("/workspace/apps/api/src/routes/users.ts"));
        assert!(result.metadata.before_tokens >= result.metadata.after_tokens);
        // Should now actually achieve some reduction
        assert!(
            result.metadata.transformed,
            "JSON reducer should produce a shorter output. before={} after={}",
            result.metadata.before_tokens,
            result.metadata.after_tokens
        );
    }
}
