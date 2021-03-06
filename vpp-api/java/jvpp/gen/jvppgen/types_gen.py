#!/usr/bin/env python
#
# Copyright (c) 2016 Cisco and/or its affiliates.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
from string import Template

import util
import jni_gen
import dto_gen

type_template = Template("""
package $plugin_package.$type_package;

/**
 * <p>This class represents $c_type_name type definition.
 * <br>It was generated by types_gen.py based on $inputfile preparsed data:
 * <pre>
$docs
 * </pre>
 */
public final class $java_type_name {
$fields
$methods
}
""")

field_template = Template("""    public $type $name;\n""")


def generate_type_fields(type_definition):
    """
    Generates fields for class representing typeonly definition
    :param type_definition: python representation of typeonly definition
    :return: string representing class fields
    """
    fields = ""
    for t in zip(type_definition['types'], type_definition['args']):
        field_name = util.underscore_to_camelcase(t[1])
        fields += field_template.substitute(type=util.jni_2_java_type_mapping[t[0]],
                                            name=field_name)
    return fields

object_struct_setter_template = Template("""
    {
        jclass ${field_reference_name}Class = (*env)->FindClass(env, "${class_FQN}");
        memset (&(mp->${c_name}), 0, sizeof (mp->${c_name}));
        ${struct_initialization}
    }
""")

object_array_struct_setter_template = Template("""
    {
        jclass ${field_reference_name}ArrayElementClass = (*env)->FindClass(env, "${class_FQN}");
        if (${field_reference_name}) {
            size_t _i;
            jsize cnt = (*env)->GetArrayLength (env, ${field_reference_name});
            ${field_length_check}
            for (_i = 0; _i < cnt; _i++) {
                jobject ${field_reference_name}ArrayElement = (*env)->GetObjectArrayElement(env, ${field_reference_name}, _i);
                memset (&(mp->${c_name}[_i]), 0, sizeof (mp->${c_name}[_i]));
                ${struct_initialization}
            }
        }
    }
""")

object_dto_field_setter_template = Template("""
    {
        jclass ${field_reference_name}Class = (*env)->FindClass(env, "${class_FQN}");
        jmethodID ${field_reference_name}Constructor = (*env)->GetMethodID(env, ${field_reference_name}Class, "<init>", "()V");
        jobject ${field_reference_name} = (*env)->NewObject(env, ${field_reference_name}Class,  ${field_reference_name}Constructor);
        ${type_initialization}
        (*env)->SetObjectField(env, dto, ${field_reference_name}FieldId, ${field_reference_name});
    }
""")

object_array_dto_field_setter_template = Template("""
    {
        jclass ${field_reference_name}Class = (*env)->FindClass(env, "${class_FQN}");
        jobjectArray ${field_reference_name} = (*env)->NewObjectArray(env, ${field_length}, ${field_reference_name}Class, 0);
        unsigned int _i;
        for (_i = 0; _i < ${field_length}; _i++) {
            jmethodID ${field_reference_name}Constructor = (*env)->GetMethodID(env, ${field_reference_name}Class, "<init>", "()V");
            jobject ${field_reference_name}ArrayElement = (*env)->NewObject(env, ${field_reference_name}Class,  ${field_reference_name}Constructor);
            ${type_initialization}
            (*env)->SetObjectArrayElement(env, ${field_reference_name}, _i, ${field_reference_name}ArrayElement);
        }
        (*env)->SetObjectField(env, dto, ${field_reference_name}FieldId, ${field_reference_name});
    }
""")


def generate_struct_initialization(type_def, c_name_prefix, object_name, indent):
    struct_initialization = ""
    # field identifiers
    for t in zip(type_def['types'], type_def['args'], type_def['lengths']):
        field_reference_name = "${c_name}" + util.underscore_to_camelcase_upper(t[1])
        field_name = util.underscore_to_camelcase(t[1])
        struct_initialization += jni_gen.jni_request_binding_for_type(field_type=t[0], c_name=c_name_prefix + t[1],
                                                                     field_reference_name=field_reference_name,
                                                                     field_name=field_name,
                                                                     field_length=t[2][0],
                                                                     is_variable_len_array=t[2][1],
                                                                     object_name=object_name)
    return indent + struct_initialization.replace('\n', '\n' + indent)


def generate_type_setter(handler_name, type_def, c_name_prefix, object_name, indent):
    type_initialization = ""
    for t in zip(type_def['types'], type_def['args'], type_def['lengths']):
        field_length = t[2][0]
        is_variable_len_array = t[2][1]
        length_field_type = None
        if is_variable_len_array:
            length_field_type = type_def['types'][type_def['args'].index(field_length)]
        type_initialization += jni_gen.jni_reply_handler_for_type(handler_name=handler_name,
                                                                  ref_name="${field_reference_name}",
                                                                  field_type=t[0], c_name=c_name_prefix + t[1],
                                                                  field_reference_name="${c_name}" + util.underscore_to_camelcase_upper(t[1]),
                                                                  field_name=util.underscore_to_camelcase(t[1]),
                                                                  field_length=field_length,
                                                                  is_variable_len_array=is_variable_len_array,
                                                                  length_field_type=length_field_type,
                                                                  object_name=object_name)
    return indent + type_initialization.replace('\n', '\n' + indent)


def generate_types(types_list, plugin_package, types_package, inputfile):
    """
    Generates Java representation of custom types defined in api file.
    """

    #
    if not types_list:
        print "Skipping custom types generation (%s does not define custom types)." % inputfile
        return

    print "Generating custom types"

    if not os.path.exists(types_package):
        raise Exception("%s folder is missing" % types_package)

    for type in types_list:
        c_type_name = type['name']
        java_type_name = util.underscore_to_camelcase_upper(type['name'])
        dto_path = os.path.join(types_package, java_type_name + ".java")

        fields = generate_type_fields(type)

        dto_file = open(dto_path, 'w')
        dto_file.write(type_template.substitute(plugin_package=plugin_package,
                                                type_package=types_package,
                                                c_type_name=c_type_name,
                                                inputfile=inputfile,
                                                docs=util.api_message_to_javadoc(type),
                                                java_type_name=java_type_name,
                                                fields=fields,
                                                methods=dto_gen.generate_dto_base_methods(java_type_name, type)
                                                ))

        # update type mappings:
        # todo fix vpe.api to use type_name instead of vl_api_type_name_t
        type_name = "vl_api_" + c_type_name + "_t"
        java_fqn = "%s.%s.%s" % (plugin_package, types_package, java_type_name)
        util.vpp_2_jni_type_mapping[type_name] = "jobject"
        util.vpp_2_jni_type_mapping[type_name + "[]"] = "jobjectArray"
        util.jni_2_java_type_mapping[type_name] = java_fqn
        util.jni_2_java_type_mapping[type_name + "[]"] = java_fqn + "[]"
        jni_name = java_fqn.replace('.', "/")
        jni_signature = "L" + jni_name + ";"
        util.jni_2_signature_mapping[type_name] = "L" + jni_name + ";"
        util.jni_2_signature_mapping[type_name + "[]"] = "[" + jni_signature
        util.jni_field_accessors[type_name] = "ObjectField"
        util.jni_field_accessors[type_name + "[]"] = "ObjectField"

        jni_gen.struct_setter_templates[type_name] = Template(
                object_struct_setter_template.substitute(
                        c_name="${c_name}",
                        field_reference_name="${field_reference_name}",
                        class_FQN=jni_name,
                        struct_initialization=generate_struct_initialization(type, "${c_name}.",
                                                                           "${field_reference_name}", ' ' * 4))
        )

        jni_gen.struct_setter_templates[type_name+ "[]"] = Template(
                object_array_struct_setter_template.substitute(
                        c_name="${c_name}",
                        field_reference_name="${field_reference_name}",
                        field_length_check="${field_length_check}",
                        class_FQN=jni_name,
                        struct_initialization=generate_struct_initialization(type, "${c_name}[_i].",
                                                                           "${field_reference_name}ArrayElement", ' ' * 8))
        )

        jni_gen.dto_field_setter_templates[type_name] = Template(
                object_dto_field_setter_template.substitute(
                        field_reference_name="${field_reference_name}",
                        field_length="${field_length}",
                        class_FQN=jni_name,
                        type_initialization=generate_type_setter(c_type_name, type, "${c_name}.",
                                                                 "${field_reference_name}", ' ' * 4))
        )

        jni_gen.dto_field_setter_templates[type_name + "[]"] = Template(
                object_array_dto_field_setter_template.substitute(
                        field_reference_name="${field_reference_name}",
                        field_length="${field_length}",
                        class_FQN=jni_name,
                        type_initialization=generate_type_setter(c_type_name, type, "${c_name}[_i].",
                                                                 "${field_reference_name}ArrayElement", ' ' * 8))
        )

        dto_file.flush()
        dto_file.close()

