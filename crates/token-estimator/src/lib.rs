use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ModelFamily {
    Claude,
    Codex,
    Gemini,
    Generic,
}

impl Default for ModelFamily {
    fn default() -> Self {
        Self::Claude
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct TokenEstimate {
    pub estimated_tokens: u32,
    pub lower_bound: u32,
    pub upper_bound: u32,
    pub bytes: usize,
    pub chars: usize,
    pub words: usize,
    pub lines: usize,
    pub heuristic: &'static str,
    pub model_family: ModelFamily,
}

pub fn estimate_text(text: &str, model_family: ModelFamily) -> TokenEstimate {
    let bytes = text.len();
    let chars = text.chars().count();
    let words = text.split_whitespace().count();
    let lines = text.lines().count().max(1);

    if text.is_empty() {
        return TokenEstimate {
            estimated_tokens: 0,
            lower_bound: 0,
            upper_bound: 0,
            bytes,
            chars,
            words,
            lines: 0,
            heuristic: "empty-input",
            model_family,
        };
    }

    let punctuation = text
        .chars()
        .filter(|ch| {
            matches!(
                ch,
                '{' | '}'
                    | '['
                    | ']'
                    | '('
                    | ')'
                    | ';'
                    | ':'
                    | '/'
                    | '\\'
                    | '<'
                    | '>'
                    | '='
                    | '+'
                    | '-'
                    | '*'
                    | '_'
                    | '.'
            )
        })
        .count();
    let digit_count = text.chars().filter(|ch| ch.is_ascii_digit()).count();
    let code_bias = (punctuation as f64 / chars.max(1) as f64) > 0.11
        || text.contains("::")
        || text.contains("=>")
        || text.contains("Traceback")
        || text.contains("fn ")
        || text.contains("const ");

    let chars_per_token = match (model_family, code_bias) {
        (ModelFamily::Claude, true) => 3.3,
        (ModelFamily::Claude, false) => 4.0,
        (ModelFamily::Codex, true) => 3.2,
        (ModelFamily::Codex, false) => 3.9,
        (ModelFamily::Gemini, true) => 3.5,
        (ModelFamily::Gemini, false) => 4.2,
        (ModelFamily::Generic, true) => 3.4,
        (ModelFamily::Generic, false) => 4.0,
    };

    let char_based = chars as f64 / chars_per_token;
    let word_multiplier = if code_bias { 1.45 } else { 1.28 };
    let word_based = words as f64 * word_multiplier;
    let digit_adjustment = digit_count as f64 * 0.02;
    let line_adjustment = if code_bias {
        (lines as f64 * 0.15).min(24.0)
    } else {
        (lines as f64 * 0.05).min(10.0)
    };

    let estimated = ((char_based * 0.58) + (word_based * 0.42) + digit_adjustment + line_adjustment)
        .round()
        .max(1.0) as u32;

    let spread_ratio = if chars < 120 {
        0.18
    } else if code_bias {
        0.14
    } else {
        0.12
    };
    let spread = ((estimated as f64) * spread_ratio).ceil() as u32;

    TokenEstimate {
        estimated_tokens: estimated,
        lower_bound: estimated.saturating_sub(spread),
        upper_bound: estimated + spread,
        bytes,
        chars,
        words,
        lines,
        heuristic: if code_bias {
            "blended-char-word-code-biased"
        } else {
            "blended-char-word-prose-biased"
        },
        model_family,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn estimates_empty_input() {
        let estimate = estimate_text("", ModelFamily::Claude);
        assert_eq!(estimate.estimated_tokens, 0);
    }

    #[test]
    fn code_like_input_has_nonzero_estimate() {
        let input = "fn main() {\n    println!(\"hello\");\n}\n";
        let estimate = estimate_text(input, ModelFamily::Codex);
        assert!(estimate.estimated_tokens > 5);
        assert!(estimate.upper_bound >= estimate.estimated_tokens);
    }

    #[test]
    fn prose_input_uses_prose_heuristic() {
        let input =
            "Context OS keeps transformations explicit and estimates token savings conservatively.";
        let estimate = estimate_text(input, ModelFamily::Claude);
        assert_eq!(estimate.heuristic, "blended-char-word-prose-biased");
    }
}
