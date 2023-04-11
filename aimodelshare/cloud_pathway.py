import time
import os


def upload_comp_exp_zipfile(
        data_directory,
        y_test=None,
        eval_metric_filepath=None,
        email_list=[]):
    """
    minimally requires model_filepath, preprocessor_filepath
    """
    zipfilelist = [data_directory]

    import json
    import os
    import requests
    import pandas as pd
    if eval_metric_filepath is None:
        pass
    else:
        zipfilelist.append(eval_metric_filepath)

    # need to save dict pkl file with arg name and filepaths to add
    # to zipfile

    apiurl = "https://djoehnv623.execute-api.us-east-2.amazonaws.com/prod/m"

    apiurl_eval = apiurl[:-1] + "eval"

    headers = {
        'Content-Type': 'application/json',
        'authorizationToken': json.dumps(
            {
                "token": os.environ.get("AWS_TOKEN"),
                "eval": "TEST"}),
    }
    post_dict = {"return_zip": "True"}
    zipfile = requests.post(
        apiurl_eval, headers=headers, data=json.dumps(post_dict))

    zipfileputlistofdicts = json.loads(zipfile.text)['put']

    zipfilename = list(zipfileputlistofdicts.keys())[0]

    from zipfile import ZipFile
    import os
    from os.path import basename
    import tempfile

    wkingdir = os.getcwd()

    tempdir = tempfile.gettempdir()

    zipObj = ZipFile(tempdir + "/" + zipfilename, 'w')
    # Add multiple files to the zip

    for i in zipfilelist:
        for dirname, subdirs, files in os.walk(i):
            zipObj.write(dirname)
            for filename in files:
                zipObj.write(os.path.join(dirname, filename))
        # zipObj.write(i)

    # add object to pkl file pathway here. (saving y label data)
    import pickle

    if y_test is None:
        pass
    else:
        with open(tempdir + "/" + 'ytest.pkl', 'wb') as f:
            pickle.dump(y_test, f)

        os.chdir(tempdir)
        zipObj.write('ytest.pkl')

    if isinstance(email_list, list):
        with open(tempdir + "/" + 'emaillist.pkl', 'wb') as f:
            pickle.dump(email_list, f)

        os.chdir(tempdir)
        zipObj.write('emaillist.pkl')
    else:
        pass

    # close the Zip File
    os.chdir(wkingdir)

    zipObj.close()

    import ast

    finalzipdict = ast.literal_eval(
        zipfileputlistofdicts[zipfilename])

    url = finalzipdict['url']
    fields = finalzipdict['fields']

    # save files from model deploy to zipfile in tempdir before
    # loading to s3

    # Load zipfile to s3
    with open(tempdir + "/" + zipfilename, 'rb') as f:
        files = {'file': (tempdir + "/" + zipfilename, f)}
        http_response = requests.post(
            url, data=fields, files=files)
    return zipfilename


def deployment_output_information():
    import os
    import sys

    sys.stdout.write(
        "[===                                  ] Progress: 5% - Accessing cloud, uploading resources...")
    sys.stdout.flush()
    time.sleep(15)
    sys.stdout.write('\r')
    sys.stdout.write(
        "[========                             ] Progress: 30% - Building serverless functions and updating permissions...")
    sys.stdout.flush()
    time.sleep(15)
    sys.stdout.write('\r')
    sys.stdout.write(
        "[============                         ] Progress: 40% - Creating custom containers...                        ")
    sys.stdout.flush()
    time.sleep(15)
    sys.stdout.write('\r')
    sys.stdout.write(
        "[==========================           ] Progress: 75% - Deploying prediction API...                          ")
    sys.stdout.flush()
    time.sleep(10)
    sys.stdout.write('\r')
    sys.stdout.write(
        "[================================     ] Progress: 90% - Configuring prediction API...                          ")
    sys.stdout.flush()
    time.sleep(10)


def run_deployment_code(
        model_filepath,
        model_type,
        private,
        categorical,
        y_train,
        preprocessor_filepath,
        example_data,
        custom_libraries,
        image,
        reproducibility_env_filepath,
        memory,
        timeout,
        email_list,
        pyspark_support,
        input_dict,
        print_output):
    def upload_playground_zipfile(
            model_filepath=None,
            preprocessor_filepath=None,
            y_train=None,
            example_data=None):
        """
      minimally requires model_filepath, preprocessor_filepath
      """
        import json
        import os
        import requests
        import pandas as pd
        wkingdir = os.getcwd()
        if os.path.dirname(model_filepath) == '':
            model_filepath = wkingdir + "/" + model_filepath
        else:
            pass

        if os.path.dirname(preprocessor_filepath) == '':
            preprocessor_filepath = wkingdir + "/" + preprocessor_filepath
        else:
            pass
        zipfilelist = [model_filepath, preprocessor_filepath]

        if any([isinstance(example_data, pd.DataFrame), isinstance(
                example_data, pd.Series), example_data is None]):
            pass
        else:
            if os.path.dirname(example_data) == '':
                example_data = wkingdir + "/" + example_data
            else:
                pass
            zipfilelist.append(example_data)

        # need to save dict pkl file with arg name and filepaths to
        # add to zipfile

        apiurl = "https://djoehnv623.execute-api.us-east-2.amazonaws.com/prod/m"

        apiurl_eval = apiurl[:-1] + "eval"

        headers = {
            'Content-Type': 'application/json',
            'authorizationToken': json.dumps(
                {
                    "token": os.environ.get("AWS_TOKEN"),
                    "eval": "TEST"}),
        }
        post_dict = {"return_zip": "True"}
        zipfile = requests.post(
            apiurl_eval, headers=headers, data=json.dumps(post_dict))

        zipfileputlistofdicts = json.loads(zipfile.text)['put']

        zipfilename = list(zipfileputlistofdicts.keys())[0]

        from zipfile import ZipFile
        import os
        from os.path import basename
        import tempfile

        wkingdir = os.getcwd()

        tempdir = tempfile.gettempdir()

        zipObj = ZipFile(tempdir + "/" + zipfilename, 'w')
        # Add multiple files to the zip
        for i in zipfilelist:
            zipObj.write(i)

        # add object to pkl file pathway here. (saving y label
        # data)
        import pickle

        if y_train is None:
            pass
        else:
            with open(tempdir + "/" + 'ytrain.pkl', 'wb') as f:
                pickle.dump(y_train, f)

            os.chdir(tempdir)
            zipObj.write('ytrain.pkl')

        if any([isinstance(example_data, pd.DataFrame),
                isinstance(example_data, pd.Series)]):
            if isinstance(example_data, pd.Series):
                example_data = example_data.to_frame()
            else:
                pass
            with open(tempdir + "/" + 'exampledata.pkl', 'wb') as f:
                pickle.dump(example_data, f)

            os.chdir(tempdir)
            zipObj.write('exampledata.pkl')
        else:
            pass

        # close the Zip File
        os.chdir(wkingdir)

        zipObj.close()

        import ast

        finalzipdict = ast.literal_eval(
            zipfileputlistofdicts[zipfilename])

        url = finalzipdict['url']
        fields = finalzipdict['fields']

        # save files from model deploy to zipfile in tempdir before
        # loading to s3

        # Load zipfile to s3
        with open(tempdir + "/" + zipfilename, 'rb') as f:
            files = {'file': (tempdir + "/" + zipfilename, f)}
            http_response = requests.post(
                url, data=fields, files=files)
        return zipfilename

    deployzipfilename = upload_playground_zipfile(
        model_filepath, preprocessor_filepath, y_train, example_data)

    # if aws arg = false, do this, otherwise do aws code
    # create deploy code_string
    def nonecheck(objinput=""):
        if isinstance(objinput, str):
            if objinput is None:
                objinput = "None"
            else:
                objinput = "'/tmp/" + objinput + "'"
        else:
            objinput = 'example_data'
        return objinput

    deploystring = self.class_string.replace(",aws=False", "") + "." + "deploy('/tmp/" + model_filepath + "','/tmp/" + \
                   preprocessor_filepath + "'," + 'y_train' + "," + nonecheck(example_data) + ",input_dict=" + str(
        input_dict) + ')'
    import requests
    import json

    api_url = "https://z4kvag4sxdnv2mvs2b6c4thzj40bxnuw.lambda-url.us-east-2.on.aws/"

    data = json.dumps(
        {
            "code": """from aimodelshare import ModelPlayground;myplayground=""" +
                    deploystring,
            "zipfilename": deployzipfilename,
            "username": os.environ.get("username"),
            "password": os.environ.get("password"),
            "token": os.environ.get("JWT_AUTHORIZATION_TOKEN"),
            "s3keyid": "xrjpv1i7xe"})

    headers = {"Content-Type": "application/json"}

    response = requests.request(
        "POST", api_url, headers=headers, data=data)
    # Print response
    global successful_deployment_info340893124738241023

    result = json.loads(response.text)
    successful_deployment_info340893124738241023 = result

    modelplaygroundurlid = json.loads(
        result['body'])[-7].replace("Playground Url: ", "").strip()
    try:
        self.playground_url = modelplaygroundurlid[1:-1]
    except BaseException:
        import json
        self.playground_url = json.loads(modelplaygroundurlid)
        pass

def cloud_deploy(model_filepath,
            model_type,
            private,
            categorical,
            y_train,
            preprocessor_filepath,
            example_data,
            custom_libraries,
            image,
            reproducibility_env_filepath,
            memory,
            timeout,
            email_list,
            pyspark_support,
            input_dict,
            print_output):

    from threading import Thread

    thread_running = True
    t1 = Thread(target=deployment_output_information)
    t1.start()

    t2 = Thread(
        target=run_deployment_code(
            model_filepath=model_filepath,
            model_type=model_type,
            private=private,
            categorical=categorical,
            y_train=y_train,
            preprocessor_filepath=preprocessor_filepath,
            example_data=example_data,
            custom_libraries=custom_libraries,
            image=image,
            reproducibility_env_filepath=reproducibility_env_filepath,
            memory=memory,
            timeout=timeout,
            email_list=email_list,
            pyspark_support=pyspark_support,
            input_dict=input_dict,
            print_output=print_output))

    t2.start()

    t2.join()  # interpreter will wait until your process get completed or terminated
    # clear last output
    import os
    import sys

    def cls():
        os.system('cls' if os.name == 'nt' else 'clear')

    # now, to clear the screen
    cls()
    from IPython.display import clear_output
    clear_output()
    sys.stdout.write('\r')
    sys.stdout.write(
        "[=====================================] Progress: 100% - Complete!                                            ")
    sys.stdout.flush()
    import json
    print(
        "\n" + json.loads(successful_deployment_info340893124738241023['body'])[-8] + "\n")
    print("View live playground now at:\n" + \
          json.loads(successful_deployment_info340893124738241023['body'])[-1])

    print("\nConnect to your playground in Python:\n")
    print("myplayground=ModelPlayground(playground_url=" +
          json.loads(successful_deployment_info340893124738241023['body'])[-7].replace("Playground Url: ",
                                                                                       "").strip() + ")")

    thread_running = False


def cloud_competition():

    print(
        "Creating your Model Playground Competition...\nEst. completion: ~1 minute\n")
    if input_dict is None:
        print("\n--INPUT COMPETITION DETAILS--\n")

        aishare_competitionname = input("Enter competition name:")
        aishare_competitiondescription = input(
            "Enter competition description:")

        print("\n--INPUT DATA DETAILS--\n")
        print(
            "Note: (optional) Save an optional LICENSE.txt file in your competition data directory to make users aware of any restrictions on data sharing/usage.\n")

        aishare_datadescription = input(
            "Enter data description (i.e.- filenames denoting training and test data, file types, and any subfolders where files are stored):")

        aishare_datalicense = input(
            "Enter optional data license descriptive name (e.g.- 'MIT, Apache 2.0, CC0, Other, etc.'):")

        input_dict = {
            "competition_name": aishare_competitionname,
            "competition_description": aishare_competitiondescription,
            "data_description": aishare_datadescription,
            "data_license": aishare_datalicense}
    else:
        pass

    # model competition files
    from aimodelshare.cloud_pathway import upload_comp_exp_zipfile
    compzipfilename = upload_comp_exp_zipfile(
        data_directory, y_test, eval_metric_filepath, email_list)

    # if aws arg = false, do this, otherwise do aws code
    # create deploy code_string
    def nonecheck(objinput=""):
        if objinput is None:
            objinput = "None"
        else:
            objinput = "'/tmp/" + objinput + "'"
        return objinput

    playgroundurlcode = "playground_url='" + self.playground_url + "'"
    compstring = self.class_string.replace(",aws=False", "").replace("playground_url=None",
                                                                     playgroundurlcode) + "." + "create_competition('/tmp/" + data_directory + "'," + 'y_test' + "," + nonecheck(
        eval_metric_filepath) + "," + 'email_list' + ",input_dict=" + str(input_dict) + ')'

    import base64
    import requests
    import json

    api_url = "https://z4kvag4sxdnv2mvs2b6c4thzj40bxnuw.lambda-url.us-east-2.on.aws/"

    data = json.dumps(
        {
            "code": """from aimodelshare import ModelPlayground;myplayground=""" +
                    compstring,
            "zipfilename": compzipfilename,
            "username": os.environ.get("username"),
            "password": os.environ.get("password"),
            "token": os.environ.get("JWT_AUTHORIZATION_TOKEN"),
            "s3keyid": "xrjpv1i7xe"})

    headers = {"Content-Type": "application/json"}

    response = requests.request(
        "POST", api_url, headers=headers, data=data)
    result = json.loads(response.text)
    printoutlist = json.loads(result['body'])
    printoutlistfinal = printoutlist[2:len(printoutlist)]
    print("\n")
    for i in printoutlistfinal:
        print(i)