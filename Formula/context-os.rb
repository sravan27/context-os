class ContextOs < Formula
  desc "Every proven Claude Code token optimization in one command"
  homepage "https://github.com/sravan27/context-os"
  url "https://github.com/sravan27/context-os/archive/refs/tags/v1.1.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_SHA256_ON_RELEASE"
  license "MIT"
  head "https://github.com/sravan27/context-os.git", branch: "main"

  depends_on "rust" => :build

  def install
    system "cargo", "install", *std_cargo_args(path: "apps/cli")

    # Install the zero-dependency setup script as well, so users can call
    # `context-os-setup` directly without needing curl.
    bin.install "setup.sh" => "context-os-setup"

    # Install examples + skills for reference
    pkgshare.install "examples"
    pkgshare.install "CONTRIBUTING.md"
    pkgshare.install "README.md"
  end

  test do
    # --measure is side-effect-free and should work in any dir
    system "#{bin}/context-os-setup", "--measure"

    # Binary should respond to --help
    assert_match "context-os", shell_output("#{bin}/context-os --help")
  end
end
