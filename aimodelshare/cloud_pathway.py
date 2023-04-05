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