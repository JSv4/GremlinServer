import yaml
import io
import ast
from codecs import encode, decode
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from pyaml import unicode
from yaml.representer import SafeRepresenter
from .models import PythonScript

#######################################################################################################################
##  YAML Formatters
#######################################################################################################################

# Heavily based on: https://stackoverflow.com/questions/6432605/any-yaml-libraries-in-python-that-support-dumping-of-long-strings-as-block-liter

# class folded_str(str): pass
# class literal_str(str): pass
#
# def change_style(style, representer):
#     def new_representer(dumper, data):
#         scalar = representer(dumper, data)
#         scalar.style = style
#         return scalar
#     return new_representer


# # represent_str does handle some corner cases, so use that
# # instead of calling represent_scalar directly
# represent_folded_str = change_style('>', SafeRepresenter.represent_str)
# represent_literal_str = change_style('|', SafeRepresenter.represent_str)
#
# yaml.add_representer(folded_str, represent_folded_str)
# yaml.add_representer(literal_str, represent_literal_str)
#
# class folded_unicode(unicode): pass
# class literal_unicode(unicode): pass
#
# def folded_unicode_representer(dumper, data):
#     return dumper.represent_scalar(u'tag:yaml.org,2002:str', data, style='>')
# def literal_unicode_representer(dumper, data):
#     return dumper.represent_scalar(u'tag:yaml.org,2002:str', data, style='|')
#
# yaml.add_representer(folded_unicode, folded_unicode_representer)
# yaml.add_representer(literal_unicode, literal_unicode_representer)

# class quoted(str):
#     pass
#
# def quoted_presenter(dumper, data):
#     return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='"')
#
# yaml.add_representer(quoted, quoted_presenter)
#
# class literal(str):
#     pass
#
# def literal_presenter(dumper, data):
#     return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
#
# yaml.add_representer(literal, literal_presenter)


# def str_presenter(dumper, data):
#   if len(data.splitlines()) > 1:  # check for multiline string
#     return dumper.represent_scalar('tag:yaml.org,2002:str', data, style='|')
#   return dumper.represent_scalar('tag:yaml.org,2002:str', data)
#
# yaml.add_representer(str, str_presenter)

#######################################################################################################################
##  Script Exporter
#######################################################################################################################

# HUGE thanks to Ruamel.yaml for making a more user friendly Python YAML library AND for this SO post
# https://stackoverflow.com/questions/50852735/how-to-use-ruamel-yaml-to-dump-literal-scalars
# Which gave me a point in the right direction to figure out to use a literal scalar.
def exportScriptYAML(scriptId):

    try:

        script = PythonScript.objects.get(pk=scriptId)

        print("Raw script:")
        print(script.script)

        print("Test Script")
        print("import json\ndef runShit(rawJson):\n\treturn json.loads(rawJson)")

        data = {
            'id': script.id,
            'name': script.name,
            'human_name': script.human_name,
            'type': script.type,
            'mode': script.mode,
            'description': script.description,
            'supported_file_types': script.supported_file_types,
            'script': LiteralScalarString(script.script),
            'required_packages': script.required_packages,
            'setup_script': script.setup_script,
            'env_variables': script.env_variables,
            'schema': script.schema
        }

        myYaml = io.StringIO()
        yaml = YAML()
        yaml.preserve_quotes = False
        yaml.dump(data, myYaml)

        return myYaml.getvalue()


        #Review this: http://blogs.perl.org/users/tinita/2018/03/strings-in-yaml---to-quote-or-not-to-quote.html
        #Possible solution: https://stackoverflow.com/questions/8640959/how-can-i-control-what-scalar-form-pyyaml-uses-for-my-data

    except Exception as e:
        print(f"Error exporting script YAML: {e}")
        return ""
