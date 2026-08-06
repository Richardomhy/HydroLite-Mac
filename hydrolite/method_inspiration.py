from hydrolite.research_registry import NOTICE, write_research_outputs


def build_method_inspiration_report(output_dir="output/research_methods"):
    return write_research_outputs(output_dir)


__all__ = ["NOTICE", "build_method_inspiration_report"]
