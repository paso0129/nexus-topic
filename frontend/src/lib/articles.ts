import { promises as fs } from 'fs';
import path from 'path';

export interface ArticleIndex {
  slug: string;
  title: string;
  meta_description: string;
  reading_time: number;
  keywords: string[];
  created_at: string;
  topic: string;
}

export interface Article {
  slug: string;
  title: string;
  meta_description: string;
  content: string;
  keywords: string[];
  reading_time: number;
  word_count: number;
  topic: string;
  created_at: string;
  updated_at: string;
  published: boolean;
  featured_image?: string;
  author: {
    name: string;
    bio: string;
  };
  source_data?: any;
}

const articlesDirectory = path.join(process.cwd(), 'public', 'articles');

export async function getArticlesIndex(): Promise<ArticleIndex[]> {
  try {
    const indexPath = path.join(articlesDirectory, 'index.json');
    const fileContents = await fs.readFile(indexPath, 'utf8');
    const articles = JSON.parse(fileContents) as ArticleIndex[];
    return articles;
  } catch (error) {
    console.error('Error reading articles index:', error);
    return [];
  }
}

export async function getArticle(slug: string): Promise<Article | null> {
  try {
    const filePath = path.join(articlesDirectory, `${slug}.json`);
    const fileContents = await fs.readFile(filePath, 'utf8');
    const article = JSON.parse(fileContents) as Article;
    return article;
  } catch (error) {
    console.error(`Error reading article ${slug}:`, error);
    return null;
  }
}

export async function getAllArticles(): Promise<Article[]> {
  try {
    const files = await fs.readdir(articlesDirectory);
    const jsonFiles = files.filter((file) => file.endsWith('.json') && file !== 'index.json');

    const articles = await Promise.all(
      jsonFiles.map(async (file) => {
        const slug = file.replace('.json', '');
        const article = await getArticle(slug);
        return article;
      })
    );

    return articles.filter((article): article is Article => article !== null);
  } catch (error) {
    console.error('Error reading all articles:', error);
    return [];
  }
}
