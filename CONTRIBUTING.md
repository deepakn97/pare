# Contributing to `pare`

# Get Started!

Ready to contribute? Here's how to set up the Proactive Agent Sandbox (`pare`) for local development.
Please note this documentation assumes you already have `uv` and `Git` installed and ready to go.

1. Fork the `pare` repo on GitHub.

2. Clone your fork locally:

```bash
cd <directory_in_which_repo_should_be_created>
git clone git@github.com:YOUR_NAME/pare.git
```

3. Now we need to install the environment. Navigate into the directory

```bash
cd pare
```

Then, install and activate the environment with:

```bash
uv sync
```

4. Install pre-commit to run linters/formatters at commit time:

```bash
uv run pre-commit install
```

5. Create a branch for local development:

```bash
git checkout -b name-of-your-bugfix-or-feature
```

Now you can make your changes locally.

6. Don't forget to add test cases for your added functionality to the `tests` directory.

7. When you're done making changes, check that your changes pass the formatting tests.

```bash
make check
```

Now, validate that all unit tests are passing:

```bash
make test
```

9. Before raising a pull request you should also run tox.
   This will run the tests across different versions of Python:

```bash
tox
```

This requires you to have multiple versions of python installed.
This step is also triggered in the CI/CD pipeline, so you could also choose to skip this step locally.

10. Commit your changes and push your branch to GitHub:

```bash
git add .
git commit -m "Your detailed description of your changes."
git push origin name-of-your-bugfix-or-feature
```

11. Submit a pull request through the GitHub website.

# Code Style Guidelines

When contributing to this project, please follow these coding conventions:

1. **Use f-strings for all string formatting and manipulation**
   - Use f-strings instead of `%` formatting or `.format()`
   - Examples:
     ```python
     # Good
     logger.debug(f"Processing {count} items from {source}")
     message = f"User {user.name} completed task {task.id}"

     # Avoid
     logger.debug("Processing %d items from %s", count, source)
     message = "User {} completed task {}".format(user.name, task.id)
     ```

2. **Follow existing patterns in the codebase**
   - Check similar files for conventions before implementing new features
   - Maintain consistency with Meta-ARE base framework patterns

# Pull Request Guidelines

Before you submit a pull request, check that it meets these guidelines:

1. The pull request should include tests.

2. If the pull request adds functionality, the docs should be updated.
   Put your new functionality into a function with a docstring, and add the feature to the list in `README.md`.
